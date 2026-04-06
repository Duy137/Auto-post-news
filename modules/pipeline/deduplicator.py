import json
import os
import re
import logging
from typing import List, Set, Dict, Any, Tuple, Optional

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import Article
from modules.state_manager import get_recent_articles_for_dedup, create_event_root, log_article_event_root
from modules.express.fingerprint import extract_fingerprints
from config import DEDUP_CONFIG

logger = logging.getLogger(__name__)

# Đọc từ config — có thể tune mà không cần sửa code
SIMILARITY_THRESHOLD = DEDUP_CONFIG["similarity_threshold"]  # Mặc định: 0.38

import uuid
from abc import ABC, abstractmethod

class EventSimilarityInterface(ABC):
    @abstractmethod 
    def calculate_similarity(self, article_a: Dict[str, Any], article_b: Dict[str, Any]) -> float:
        pass

# [GIỮ LẠI ĐỂ THAM KHẢO] JaccardSimilarity thuần — không dùng trong pipeline chính nữa
class JaccardSimilarity(EventSimilarityInterface):
    def calculate_similarity(self, article_a: Dict[str, Any], article_b: Dict[str, Any]) -> float:
        tokens_a = get_article_tokens(article_a.get('title', ''), article_a.get('link', ''))
        tokens_b = get_article_tokens(article_b.get('title', ''), article_b.get('link', ''))
        return calculate_jaccard_similarity(tokens_a, tokens_b)

def match_historical_roots(new_article: Dict[str, Any], recent_articles: List[Dict[str, Any]], similarity_engine: EventSimilarityInterface) -> Tuple[Optional[str], int]:
    """Tìm event_root_id trong quá khứ. Trả về (root_id, root_created_ts)."""
    current_time = new_article.get('published_ts', 0)
    time_window = 5 * 24 * 3600
    
    best_root_id = None
    best_created_ts = 0
    best_sim = 0.0
    
    for seen_art in recent_articles:
        if abs(current_time - seen_art.get('published_ts', 0)) <= time_window:
            sim = similarity_engine.calculate_similarity(new_article, seen_art)
            if sim >= 0.25 and sim > best_sim:
                best_sim = sim
                best_root_id = seen_art.get("event_root_id")
                best_created_ts = seen_art.get("root_created_ts", seen_art.get("published_ts", 0))
                
    return best_root_id, best_created_ts

def get_words(text: str) -> Set[str]: #Giặt sạch văn bản. Ví dụ chuyền vào "Bitcoin, hit $100k!!", nó xóa sạch dấu câu, viết thường, cắt cụm, bỏ từ ngắn, trả ra {"bitcoin", "100k"}
    """Extract set các từ khóa đã lowercase từ chuỗi, bỏ qua dấu câu."""
    if not text:
        return set()
    # Chỉ giữ lại a-z, 0-9, "-" và "_" (giữ cho slug)
    clean_text = re.sub(r'[^a-zA-Z0-9\s\-_]', ' ', text.lower())
    # Chia theo khoảng trắng, "-" và "_"
    words = {w for w in re.split(r'[\s\-_]+', clean_text) if len(w) > 2}
    return words

def get_slug_from_url(url: str) -> str: #Lấy phần đuôi URL (ví dụ: /bitcoin-hits-100k-in-2025) và giặt sạch nó.
    """Lấy phần path cuối cùng của URL (chứa keywords nhất)."""
    from urllib.parse import urlparse
    path = urlparse(url).path
    # Lấy segment cuối cùng
    segments = [s for s in path.split('/') if s]
    return segments[-1] if segments else ""

def get_article_tokens(title: str, url: str) -> Set[str]: #Tổng hợp các từ khóa vàng từ cả Tiêu đề lẫn URL Slug. Gom thành 1 rổ (Set) từ khóa đại diện cho "Linh hồn" của bài báo.
    """Kết hợp token từ cả Title và URL Slug."""
    title_words = get_words(title)
    slug = get_slug_from_url(url)
    slug_words = get_words(slug)
    return title_words.union(slug_words)

def calculate_jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float: #Thực hiện thuật toán toán học Jaccard. Lấy (Số từ giống nhau) chia cho (Tổng số từ của 2 bên).
    """Tính Jaccard Similarity: Intersection / Union."""
    if not set_a or not set_b:
        return 0.0
    
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    
    return intersection / union if union > 0 else 0.0

def normalize_text_phrases(text: str) -> str:
    """Bước 1: Thay thế phrase nhiều chữ trong raw text TRƯỚC KHI tokenize.
    Dùng regex word boundary để tránh match sai substring.
    Ví dụ: "regulatory" sẽ KHÔNG bị thay thành "sec" dù chứa "regulator".
    """
    text_lower = text.lower()
    for phrase, replacement in DEDUP_CONFIG["normalization_phrases"].items():
        pattern = r"\b" + re.escape(phrase) + r"\b"
        text_lower = re.sub(pattern, replacement, text_lower)
    return text_lower

def normalize_tokens(tokens: Set[str]) -> Set[str]:
    """Bước 2: Normalize từng token đơn SAU KHI tokenize (BTC→bitcoin, ETH→ethereum...)."""
    norm_map = DEDUP_CONFIG["normalization_tokens"]
    return {norm_map.get(t, t) for t in tokens}

class EnhancedSimilarity(EventSimilarityInterface):
    """
    [V2.0] Hybrid similarity = (entity_weight × entity_sim) + (token_weight × jaccard).
    - Entity similarity: đo độ trùng tên người/tổ chức/token giữa 2 bài (signal mạnh)
    - Token Jaccard: đo độ trùng từ phổ thông (signal phụ)
    Weights và threshold có thể tune trong DEDUP_CONFIG (config.py).
    """
    def calculate_similarity(self, article_a: Dict[str, Any], article_b: Dict[str, Any]) -> float:
        title_a = article_a.get("title", "")
        title_b = article_b.get("title", "")

        # Bước 1: Token Jaccard (có normalize phrase + token)
        norm_a = normalize_text_phrases(title_a)
        norm_b = normalize_text_phrases(title_b)
        slug_a = get_slug_from_url(article_a.get("link", ""))
        slug_b = get_slug_from_url(article_b.get("link", ""))
        tokens_a = normalize_tokens(get_words(norm_a).union(get_words(slug_a)))
        tokens_b = normalize_tokens(get_words(norm_b).union(get_words(slug_b)))
        jaccard = calculate_jaccard_similarity(tokens_a, tokens_b)

        # Bước 2: Entity similarity (dùng express_fingerprint đã có sẵn)
        raw_ents_a = set(extract_fingerprints(title_a))
        raw_ents_b = set(extract_fingerprints(title_b))
        # Trim fingerprint nhiều chữ xuống còn 2 chữ đầu để tránh CamelCase over-matching.
        # Ví dụ: "david sacks wraps up crypto" -> "david sacks" để khớp với bài kia.
        def trim_fp(fps):
            return {' '.join(fp.split()[:2]) for fp in fps}
        # Áp dụng normalization_tokens (btc→bitcoin) lên entity strings
        norm_map = DEDUP_CONFIG["normalization_tokens"]
        ents_a = {norm_map.get(e, e) for e in trim_fp(raw_ents_a)}
        ents_b = {norm_map.get(e, e) for e in trim_fp(raw_ents_b)}

        intersection = ents_a & ents_b
        # [FIX] Dùng max thay vì min: tránh trường hợp bài chỉ có 1 entity chung (bitcoin)
        # nhưng entity_sim = 1.0 vì min(3,1)=1 → 1/1=1.0 → gom nhầm 37 bài vào 1 cluster.
        # Với max: 1/max(3,1) = 0.33 → đúng: chỉ 1/3 entities trùng.
        max_ents = max(len(ents_a), len(ents_b), 1)
        entity_sim = len(intersection) / max_ents
        entity_sim = min(entity_sim, 1.0)  # clamp về [0, 1]


        # Bước 3: Weighted blend — bounded [0, 1]
        e_w = DEDUP_CONFIG["entity_weight"]
        t_w = DEDUP_CONFIG["token_weight"]
        score = e_w * entity_sim + t_w * jaccard

        logger.debug(
            f"[DEDUP SIM] score={score:.2f} | entity={entity_sim:.2f} | jaccard={jaccard:.2f} | "
            f"title_A='{title_a[:60]}' | title_B='{title_b[:60]}' | "
            f"ents_A={ents_a} | ents_B={ents_b}"
        )

        return score


def deduplicate_articles(articles: List[Article]) -> List[Article]:
    """
    Main Phase 2 Pipeline function.
    Chuyển thành Event-Level Clustering. Gom nhóm bài cùng sự kiện và chọn Lead Article.
    Nối ghép Narrative Continuity bằng event_root_id.
    """
    logger.info(f"Starting Event-Level Clustering for {len(articles)} articles.")
    
    # Kéo lịch sử từ SQLite (articles table) thay vì file JSON mồ côi
    recent_articles = get_recent_articles_for_dedup(hours=120)
    
    # [V2.0] Dùng EnhancedSimilarity thay JaccardSimilarity thuần
    similarity_engine = EnhancedSimilarity()
    
    unique_articles: List[Article] = []
    
    for article in articles:
        # Note: Phase 1 (Insert) đã tự loại bỏ bài trùng ID nhờ SQLite UNIQUE Constraint,
        # Nên ở đây chúng ta bỏ qua màng lọc seen_ids.
            
        # 2. EVENT-LEVEL CLUSTERING
        is_clustered = False
        for lead_art in unique_articles:
            sim = similarity_engine.calculate_similarity(article, lead_art)
            if sim >= SIMILARITY_THRESHOLD:
                is_clustered = True
                lead_art["cluster_size"] = lead_art.get("cluster_size", 1) + 1
                break
                
        # Đồng thời kiểm tra chéo 48h
        if not is_clustered:
            time_window_48h = 48 * 3600
            current_time = article.get('published_ts', 0)
            relevant_articles = [
                art for art in recent_articles 
                if abs(current_time - art.get('published_ts', 0)) <= time_window_48h
            ]
            for seen_art in relevant_articles:
                sim = similarity_engine.calculate_similarity(article, seen_art)
                if sim >= SIMILARITY_THRESHOLD:
                    is_clustered = True
                    # Tìm lại Lead của nó nếu được (trong thực tế, seen_art là Lead trong quá khứ)
                    # Ở version này, đợt quét sẽ bỏ qua article này.
                    break

        if is_clustered:
            logger.debug(f"[Event Cluster] Gom bài '{article['title']}' vào Cụm hiện tại.")
            continue
            
        # 3. NARRATIVE CONTINUITY
        root_id, root_created_ts = match_historical_roots(article, recent_articles, similarity_engine)
        if not root_id:
            root_id = f"evt_{str(uuid.uuid4())[:8]}" # Tạo Root ID mới
            root_created_ts = article.get("published_ts", 0)
            
        article["event_root_id"] = root_id
        article["root_created_ts"] = root_created_ts
        article["cluster_size"] = 1
        
        # Ghi nhận root_id mới xuống DB
        create_event_root(root_id, article["title"])
        log_article_event_root(article["id"], root_id)
        
        # Passed all filters -> Trở thành Lead Article của Cụm
        unique_articles.append(article)
        
        # Bổ sung bài này vào recent window loop (tránh query DB liên tục)
        recent_articles.append({
            "title": article["title"],
            "link": article["link"],
            "published_ts": article["published_ts"],
            "event_root_id": root_id,
            "root_created_ts": root_created_ts
        })
        
    
    logger.info(f"Phase 2 Complete: Formed {len(unique_articles)} Event Clusters (Lead Articles).")
    return unique_articles

if __name__ == "__main__":
    # ------------------ MÔ PHỎNG INPUT / OUTPUT ------------------
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    print("\n[MÔ PHỎNG PHASE 2: DEDUPLICATOR]")
    
    # Fake history file start (Reset for test)
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        
    # Dữ liệu mẫu cực nguy hiểm cho Soft Dedup cũ
    mock_articles: List[Article] = [
        # Tin 1: Bài đánh dấu gốc
        {
            "id": "hash_111", "title": "BTC reaches record high", 
            "link": "https://site.com/btc-reaches-record-high-100k", "raw_source_url": "link1", "summary": "", 
            "published_ts": 1700000000, "source_name": "TechA",
            "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 2: Title hoàn toàn khác chữ nhưng URL slug bóc ra được keyword ("btc", "100k", "record", "high")
        {
            "id": "hash_222", "title": "Bitcoin hits new ATH", 
            "link": "https://other.com/news/btc-reaches-record-high-100k-today", "raw_source_url": "link2", "summary": "", 
            "published_ts": 1700000060, "source_name": "TechB", # Đăng sau 60s
            "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 3: Vượt quá 48h (Để test O(n^2) filter)
        {
            "id": "hash_333", "title": "Bitcoin hits new ATH", 
            "link": "https://old.com/btc-reaches-record-high-100k", "raw_source_url": "link3", "summary": "", 
            "published_ts": 1700000000 + (50 * 3600), "source_name": "TechC", # 50h sau -> Qua filter vì hết hạn
            "score": None, "score_detail": None, "tweet_content": None
        }
    ]
    
    print("\n--- INPUT ARTICLES ---")
    for a in mock_articles:
        print(f"[{a['id']}] {a['title']}")
        
    print("\n--- PROCESSING ---")
    results = deduplicate_articles(mock_articles)
    
    print("\n--- OUTPUT ARTICLES (UNIQUE ONLY) ---")
    for a in results:
        print(f"✅ {a['title']}")
