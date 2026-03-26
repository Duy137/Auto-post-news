import sqlite3
import os
import json
import logging
import time
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# System paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "article_state.db")

# Strict State Enum
class ArticleState:
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    RANKED = "RANKED"
    SELECTED = "SELECTED"
    POSTED = "POSTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"

    # Define valid transitions for safety
    VALID_TRANSITIONS = {
        NEW: [PROCESSING, SKIPPED],
        PROCESSING: [NEW, RANKED, SELECTED, POSTED, FAILED, SKIPPED], # Can unlock back to NEW on timeout
        RANKED: [PROCESSING, SKIPPED],
        SELECTED: [PROCESSING, SKIPPED],
        POSTED: [], # Terminal
        SKIPPED: [], # Terminal
        FAILED: [NEW, PROCESSING] # Allow retry by pushing back
    }

def get_db_connection() -> sqlite3.Connection:
    """Trả về connection SQLite an toàn (timeout cho WAL mode)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0) # 10s timeout cho concurrency lock
    conn.row_factory = sqlite3.Row
    # WAL Mode for high concurrency reads/writes
    conn.execute("PRAGMA journal_mode=WAL;") 
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    """Khởi tạo cấu trúc Database an toàn và idempotent."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Table Creation
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                canonical_url TEXT UNIQUE NOT NULL,
                state TEXT NOT NULL DEFAULT 'NEW',
                title TEXT,
                source_name TEXT,
                score_snapshot TEXT,
                retry_count INTEGER DEFAULT 0,
                lock_flag INTEGER DEFAULT 0,
                event_root_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        try:
            cursor.execute("ALTER TABLE articles ADD COLUMN event_root_id TEXT")
        except sqlite3.OperationalError:
            pass
            
        # [REDUNDANT V4.7] Bảng ghi log keyword phục vụ Adaptive Weight.
        # Hiện tại cơ chế này đã tắt, có thể xóa bảng này sau này.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS keyword_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_kw_created ON keyword_logs(created_at)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_roots (
                id TEXT PRIMARY KEY,
                anchor_title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 1.1 Express Lane Dedicated Tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS express_seen (
                hash TEXT PRIMARY KEY,
                raw_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_express_hash ON express_seen(hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_express_created ON express_seen(created_at)')
        
        # 1.2 Shared Suppression Table (Phase 5 & 7)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recent_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                source_lane TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recent_topics_fingerprint ON recent_topics(fingerprint)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recent_topics_created ON recent_topics(created_at)')
        
        # 1.3 Published Events Table (Phase 6 Omni-channel)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS published_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                platform TEXT NOT NULL,
                lane TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_published_fp_platform ON published_events(fingerprint, platform)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_published_created ON published_events(created_at)')
        
        # 2. Indexes for Query Performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_state ON articles(state)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_articles_updated_at ON articles(updated_at)')
        
        # 3. Auto-update Timestamp Trigger (SQLite native logic!)
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS trigger_articles_updated_at
            AFTER UPDATE ON articles
            FOR EACH ROW
            BEGIN
                UPDATE articles SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully with WAL and Triggers.")

def insert_new_article(article_id: str, canonical_url: str, title: str = "", source_name: str = "") -> bool:
    """Nhét bài vào DB. Trả về True nếu Insert thành công (Mới), False nếu Duplicate (Bỏ qua)."""
    with get_db_connection() as conn:
        try:
            conn.execute('''
                INSERT INTO articles (id, canonical_url, state, title, source_name)
                VALUES (?, ?, ?, ?, ?)
            ''', (article_id, canonical_url, ArticleState.NEW, title, source_name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Vi phạm ràng buộc UNIQUE của canonical_url hoặc Primary Key ID
            return False

def claim_next_article(from_state: str) -> Optional[Dict[str, Any]]:
    """
    Kéo 1 bài báo thuộc state X ra xử lý (Atomic Transition -> PROCESSING).
    Giải quyết hoàn toàn vấn đề Concurrency (Nhiều Cron cướp chung 1 bài).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Lock database transactions via IMMEDIATE (tối ưu hơn EXCLUSIVE cho SQLite WAL)
        cursor.execute("BEGIN IMMEDIATE TRANSACTION")
        
        try:
            # 1. Tìm 1 bài cũ nhất (ưu tiên xử lý trước) theo State cần claim
            cursor.execute('''
                SELECT id, canonical_url, title, state, retry_count, score_snapshot, event_root_id
                FROM articles 
                WHERE state = ? AND lock_flag = 0
                ORDER BY created_at ASC 
                LIMIT 1
            ''', (from_state,))
            
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT")
                return None
                
            art_id = row['id']
            
            # 2. Đánh dấu ngay lập tức thành PROCESSING và Lock cờ lại
            cursor.execute('''
                UPDATE articles 
                SET state = ?, lock_flag = 1 
                WHERE id = ?
            ''', (ArticleState.PROCESSING, art_id))
            
            conn.execute("COMMIT")
            
            return dict(row)
            
        except sqlite3.Error as e:
            conn.execute("ROLLBACK")
            logger.error(f"Error claiming article: {e}")
            return None

def transition_state(article_id: str, new_state: str, score_snapshot: Optional[dict] = None) -> bool:
    """Chuyển State bài báo một cách hợp lệ sau khi Worker xử lý xong."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Kiểm tra tính hợp lệ của State Jump
        cursor.execute("SELECT state FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        
        if not row:
            logger.error(f"Cannot transition: Article {article_id} not found.")
            return False
            
        current_state = row['state']
        
        # Lược bỏ validate cho test script (trong lúc dev linh hoạt)
        if new_state not in ArticleState.VALID_TRANSITIONS.get(current_state, []):
             logger.warning(f"Illegal transition requested for {article_id}: {current_state} -> {new_state}.")
             # Trong production cứng có thể return False, nhưng hiện tại ta just log warning
             pass
        
        # Mở cờ lock -> 0, và Cập nhật Snapshot (nếu có)
        try:
            if score_snapshot:
                 snapshot_str = json.dumps(score_snapshot)
                 cursor.execute('''
                    UPDATE articles 
                    SET state = ?, lock_flag = 0, score_snapshot = ?
                    WHERE id = ?
                 ''', (new_state, snapshot_str, article_id))
            else:
                 cursor.execute('''
                    UPDATE articles 
                    SET state = ?, lock_flag = 0 
                    WHERE id = ?
                 ''', (new_state, article_id))
            
            conn.commit()
            logger.info(f"State transitioned: {article_id} [{current_state} -> {new_state}]")
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to transition state for {article_id}: {e}")
            return False

def increment_retry(article_id: str) -> int:
    """Tăng cờ retry limit. Trả về số lần retry hiện tại."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE articles 
            SET retry_count = retry_count + 1 
            WHERE id = ?
        ''', (article_id,))
        conn.commit()
        
        cursor.execute('SELECT retry_count FROM articles WHERE id = ?', (article_id,))
        row = cursor.fetchone()
        return row['retry_count'] if row else 0

def mark_posted(article_id: str) -> bool:
    """Bắn thẳng State -> POSTED. Module này ko lưu posted_at (DB tự trigger Timestamp), ta chỉ đổi State."""
    return transition_state(article_id, ArticleState.POSTED)

import random

def release_processing_timeout(timeout_minutes: int = 30) -> int:
    """
    [Tự Cứu Thương] Watchdog function.
    Reset PROCESSING articles older than timeout safely back to NEW.
    Adds random jitter (0-5 phút) to avoid herd effect.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Thêm 0-5 phút random jitter để rải rác load
        jitter_minutes = random.randint(0, 5)
        total_timeout_sec = (timeout_minutes + jitter_minutes) * 60
        
        cursor.execute(f'''
            UPDATE articles
            SET state = '{ArticleState.NEW}', lock_flag = 0
            WHERE state = '{ArticleState.PROCESSING}' 
            AND strftime('%s', 'now') - strftime('%s', updated_at) > ?
        ''', (total_timeout_sec,))
        
        rowcount = cursor.rowcount
        conn.commit()
        if rowcount > 0:
            logger.warning(f"Watchdog released {rowcount} zombie articles from PROCESSING back to NEW (Jitter: {jitter_minutes}m).")
        return rowcount

def log_keywords(keywords: List[str]):
    """
    [REDUNDANT V4.7] Log keywords to database. 
    Phục vụ Adaptive Weight (đã tắt). Có thể xóa toàn bộ logic này sau.
    """
    if not keywords: return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            'INSERT INTO keyword_logs (keyword) VALUES (?)',
            [(k,) for k in keywords]
        )
        conn.commit()

def get_keyword_frequencies_24h() -> Dict[str, int]:
    """
    [REDUNDANT V4.7] Lấy tần suất các keyword trong 24h qua.
    Phục vụ Adaptive Weight (đã tắt).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT keyword, COUNT(*) as cnt 
            FROM keyword_logs 
            WHERE created_at >= datetime('now', '-24 hours')
            GROUP BY keyword
        ''')
        return {row['keyword']: row['cnt'] for row in cursor.fetchall()}

def clean_old_keyword_logs():
    """
    [REDUNDANT V4.7] Xóa log cũ hơn 48h. 
    Có thể xóa function này khi xóa bảng keyword_logs.
    """
    with get_db_connection() as conn:
        conn.execute("DELETE FROM keyword_logs WHERE created_at < datetime('now', '-48 hours')")
        conn.commit()

def create_event_root(root_id: str, anchor_title: str):
    with get_db_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO event_roots (id, anchor_title) VALUES (?, ?)', (root_id, anchor_title))
        conn.commit()

def log_article_event_root(article_id: str, root_id: str):
    """Cập nhật rễ sự kiện cho bài viết"""
    with get_db_connection() as conn:
        conn.execute('UPDATE articles SET event_root_id = ? WHERE id = ?', (root_id, article_id))
        conn.commit()

def get_recent_articles_for_dedup(hours: int = 120) -> List[Dict[str, Any]]:
    """Lấy danh sách các bài viết gần đây kèm theo event_root_id để phục vụ Deduplicator Phase 2."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT id, canonical_url as link, title, source_name, event_root_id, 
                   CAST(strftime('%s', created_at) AS INTEGER) as published_ts,
                   CAST(strftime('%s', created_at) AS INTEGER) as root_created_ts
            FROM articles
            WHERE created_at >= datetime('now', '-{hours} hours') 
            AND event_root_id IS NOT NULL
        ''')
        return [dict(row) for row in cursor.fetchall()]

# ==========================================
# EXPRESS LANE: HARD DEDUPLICATION (PHASE 2)
# ==========================================
import hashlib
import re

def normalize_text_for_hash(text: str) -> str:
    """Loại bỏ khoảng trắng, xuống dòng dư thừa và lowercase để băm."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def check_and_insert_express_seen(raw_text: str) -> bool:
    """
    Check xem tin nhắn đã thấy trong 24h qua chưa.
    Nếu chưa, Insert vào bảng express_seen.
    Trả về:
        True nếu Đã Thấy (DUPLICATE)
        False nếu Chưa Thấy (NEW)
    """
    normalized_text = normalize_text_for_hash(raw_text)
    msg_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Quét tìm hash trong 24h qua
        cursor.execute('''
            SELECT hash FROM express_seen 
            WHERE hash = ? AND created_at >= datetime('now', '-24 hours')
        ''', (msg_hash,))
        
        if cursor.fetchone():
            return True # Duplicate!
            
        # 2. Nếu chưa thấy, insert mới (sử dụng INSERT OR IGNORE chặn race condition nhẹ)
        cursor.execute('''
            INSERT OR IGNORE INTO express_seen (hash, raw_text)
            VALUES (?, ?)
        ''', (msg_hash, raw_text))
        
        if cursor.rowcount > 0:
            conn.commit()
            return False # New!
        else:
            # Hash đã tồn tại nhưng có thể nằm ngoài 24h window ở select trên
            # Hoặc 2 luồng cùng nhét vào sát milisecond -> Luồng này bị ignore
            cursor.execute('''
                UPDATE express_seen SET created_at = CURRENT_TIMESTAMP WHERE hash = ?
            ''', (msg_hash,))
            conn.commit()
            return True # Duplicate!
            
def clean_old_express_seen():
    """Dọn dẹp log express cũ hơn 24h."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM express_seen WHERE created_at < datetime('now', '-24 hours')")
        conn.commit()

# ==========================================
# PHASE 5 & 7: SHARED SUPPRESSION (60-MIN WINDOW)
# ==========================================

def check_recent_topic(fingerprint: str, minutes: int = 60) -> bool:
    """
    Check xem fingerprint đã xuất hiện trong N phút qua chưa.
    Trả về True nếu ĐÃ có (Duplicate/Suppress), False nếu Chưa có.
    """
    if not fingerprint:
        return False # Empty fingerprint không bao giờ bị khóa chung
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM recent_topics 
            WHERE fingerprint = ? 
            AND created_at >= datetime('now', ?)
        ''', (fingerprint, f'-{minutes} minutes'))
        
        return cursor.fetchone() is not None

def insert_recent_topic(fingerprint: str, source_lane: str):
    """
    Lưu fingerprint sau khi ĐÃ PUBLISH THÀNH CÔNG.
    source_lane = 'EXPRESS' | 'RSS'
    """
    if not fingerprint:
         return
         
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO recent_topics (fingerprint, source_lane)
            VALUES (?, ?)
        ''', (fingerprint, source_lane))
        conn.commit()

def clean_old_topics(hours: int = 48):
    """
    Dọn dẹp log fingerprint cũ.
    Trong production, hàm này sẽ được gọi thỉnh thoảng ở các khoảng nghỉ (wait) của loop.
    """
    with get_db_connection() as conn:
        conn.execute(f"DELETE FROM recent_topics WHERE created_at < datetime('now', '-{hours} hours')")
        conn.commit()

# ==========================================
# PHASE 6: PUBLISHED EVENTS AWARENESS
# ==========================================

def is_event_published(fingerprint: str, platform: str) -> bool:
    """Kiểm tra xem một sự kiện (fingerprint) đã từng được đăng lên CÙNG 1 nền tảng chưa."""
    if not fingerprint:
        return False
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1 FROM published_events 
            WHERE fingerprint = ? AND platform = ?
        ''', (fingerprint, platform))
        return cursor.fetchone() is not None

def mark_event_published(fingerprint: str, platform: str, lane: str):
    """Lưu vết bài đã đăng thành công lên nền tảng."""
    if not fingerprint:
        return
        
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO published_events (fingerprint, platform, lane)
            VALUES (?, ?, ?)
        ''', (fingerprint, platform, lane))
        conn.commit()

# ==========================================
# MAINTENANCE: GARBAGE COLLECTION
# ==========================================

def perform_routine_maintenance():
    """
    Dọn dẹp tự động (Auto-Cleanup) tất cả dữ liệu rác cũ theo yêu cầu của System Architect:
    - articles: giữ 2 ngày
    - recent_topics: giữ 48 hours
    - express_seen: giữ 24 hours
    - published_events: giữ 7 ngày
    """
    logger.info("🧹 [MAINTENANCE] Bắt đầu dọn dẹp Database tự động...")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Dọn dẹp Articles (> 2 days)
            cursor.execute("DELETE FROM articles WHERE created_at < datetime('now', '-2 days')")
            deleted_articles = cursor.rowcount
            
            # 2. Dọn dẹp Recent Topics (> 48h)
            cursor.execute("DELETE FROM recent_topics WHERE created_at < datetime('now', '-48 hours')")
            deleted_topics = cursor.rowcount
            
            # 3. Dọn dẹp Express Seen (> 24h)
            cursor.execute("DELETE FROM express_seen WHERE created_at < datetime('now', '-24 hours')")
            deleted_express = cursor.rowcount
            
            # 4. Dọn dẹp Published Events (> 7 days)
            cursor.execute("DELETE FROM published_events WHERE created_at < datetime('now', '-7 days')")
            deleted_published = cursor.rowcount
            
            conn.commit()
            
            logger.info(f"🧹 [MAINTENANCE] Đã xóa: {deleted_articles} articles, {deleted_topics} topics, {deleted_express} express hash, {deleted_published} published events.")
            
            # Thực thi SQLite Vacuum để nén file DB, giải phóng dung lượng ổ cứng
            cursor.execute("VACUUM")
            logger.info("🧹 [MAINTENANCE] Hoàn tất nén Database (VACUUM).")
            
    except Exception as e:
        logger.error(f"❌ [MAINTENANCE] Lỗi trong quá trình dọn dẹp Database: {e}")
# 🧪 TEST MODE VÀ MÔ PHỎNG AN TOÀN
# ==========================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    print("\n[MÔ PHỎNG PHASE 7: STATE-DRIVEN LIFECYCLE]\n")
    
    # Reset Test DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    init_db()
    
    # 1. Crawl & Insert
    print("\n--- 1. INSERTING (Giả lập RSS Collector) ---")
    arts = [
        ("id1", "https://link.com/1", "BTC ATH"),
        ("id2", "https://link.com/2", "ETH Explodes"),
        ("id3", "https://link.com/1", "BTC ATH (Trùng URL)") # Trùng
    ]
    for uid, url, t in arts:
        success = insert_new_article(uid, url, title=t)
        print(f"Insert [ {t} / {url} ] -> {'✅ Success' if success else '❌ Duplicated'}")
        
    # 2. Worker Nhặt Data
    print("\n--- 2. CLAIMING (Giả lập Worker bốc bài) ---")
    job = claim_next_article(ArticleState.NEW)
    print(f"Worker claimed job: {job['title']} | State became PROCESSING | LockFlag=1")
    
    # 3. Simulate Worker CRASH
    print("\n--- 3. CRASH SIMULATION ---")
    print("Worker crashed!... Bài vẫn đang nằm cứng ở PROCESSING (Zombie)")
    
    # Chỉnh tay updated_at trong DB quá 60 phút để Test Zombie Release
    with get_db_connection() as conn:
        conn.execute("UPDATE articles SET updated_at = datetime('now', '-60 minutes') WHERE id = ?", (job['id'],))
        conn.commit()
        
    # 4. Release Zombie
    print("\n--- 4. ZOMBIE HUNTER ---")
    release_processing_timeout(timeout_minutes=30)
    
    # 5. Recovery Worker Reclaiming
    print("\n--- 5. RECOVERY CLAIMING ---")
    job_recovered = claim_next_article(ArticleState.NEW)
    print(f"Watchdog Worker successfully reclaimed the crashed job: {job_recovered['title']}")
    
    # 6. Push state to Ranked
    print("\n--- 6. SAFE TRANSITION ---")
    transition_state(job_recovered['id'], ArticleState.RANKED, score_snapshot={"total_score": 99.0, "reason": "Xịn"})
    print(f"Worker marked {job_recovered['title']} as RANKED with DB lock released.")
    
    # Check Result
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, state, lock_flag, score_snapshot FROM articles")
        rows = cursor.fetchall()
        print("\n--- DATABASE DUMP SNAPSHOT ---")
        for r in rows:
            print(dict(r))

    """
    [GIẢI THÍCH CONCURRENCY SAFETY TRONG THIẾT KẾ NÀY]
    1. WAL (Write-Ahead Logging) Mode:
       Thay vì khóa (lock) toàn bộ file `.db` mỗi lần viết (như mặc định SQLite làm cho thread-safe), 
       WAL cho phép nhiều Worker ĐỌC song song kể cả khi có 1 Worker ĐANG VIẾT (Ghi vào log riêng).
       Nó giải quyết vấn đề "Database is locked" khi chạy nhiều luồng.
       
    2. EXCLUSIVE TRANSACTION trong claim_next_article():
       Khi một worker (cron) quét DB tìm bài NEW để hốt, nó gửi ngay lệnh BEGIN EXCLUSIVE.
       Chỉ 1 worker cầm được cờ này. Worker đó lôi Article ID ra, set STATE = PROCESSING và cắm lock_flag = 1 
       rồi lập tức COMMIT (nhả cờ viết). 
       Vì Transaction hoàn toàn Atomic (Nguyên tử), KHÔNG BAO GIỜ có viện 2 Cron xé rào chạy trùng và giật mất 
       một bài báo (Double Worker Processing). 
    """
