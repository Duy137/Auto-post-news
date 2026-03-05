import json
import os
import re
import logging
from typing import List, Set, Dict, Any, Tuple, Optional

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Article

logger = logging.getLogger(__name__)

# Config cho deduplicator
HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seen_articles.json")
SIMILARITY_THRESHOLD = 0.45  # Khoảng 45% trùng lặp từ khóa chính là đủ để coi là duplicate vì ta đã bỏ stopwords

import uuid
from abc import ABC, abstractmethod

class EventSimilarityInterface(ABC):
    @abstractmethod
    def calculate_similarity(self, article_a: Dict[str, Any], article_b: Dict[str, Any]) -> float:
        pass

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

def load_history() -> Dict[str, Any]: #Chịu trách nhiệm Load (đọc) dữ liệu xuống ổ cứng
    """Load lịch sử các bài đã quét."""
    if not os.path.exists(HISTORY_FILE):
        return {"seen_ids": [], "recent_articles": []}
    
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading history file: {e}")
        return {"seen_ids": [], "recent_articles": []}

def save_history(history: Dict[str, Any], max_history: int = 2000): #Hàm Save tích hợp cơ chế "Rolling Window" - chỉ bo bo giữ lại dòng đuôi 2000 bản ghi mới nhất.
    """Lưu trữ ID và Titles, giữ size file không bị phình to (Rolling window)."""
    # Keep only the latest `max_history` items
    history["seen_ids"] = history["seen_ids"][-max_history:]
    history["recent_articles"] = history["recent_articles"][-max_history:]
    
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving history file: {e}")

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

def deduplicate_articles(articles: List[Article]) -> List[Article]:
    """
    Main Phase 2 Pipeline function:
    Chuyển thành Event-Level Clustering. Gom nhóm bài cùng sự kiện và chọn Lead Article.
    Nối ghép Narrative Continuity bằng event_root_id.
    """
    logger.info(f"Starting Event-Level Clustering for {len(articles)} articles.")
    
    history_data = load_history()
    seen_ids = set(history_data.get("seen_ids", []))
    recent_articles = history_data.get("recent_articles", [])
    
    similarity_engine = JaccardSimilarity()
    
    unique_articles: List[Article] = []
    
    for article in articles:
        # 1. HARD DEDUP
        if article["id"] in seen_ids:
            logger.debug(f"[Hard Dedup] Bỏ qua bài đã có ID: {article['title']}")
            continue
            
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
            seen_ids.add(article["id"]) 
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
        
        # Passed all filters -> Trở thành Lead Article của Cụm
        unique_articles.append(article)
        
        seen_ids.add(article["id"])
        recent_articles.append({
            "title": article["title"],
            "link": article["link"],
            "published_ts": article["published_ts"],
            "event_root_id": root_id,
            "root_created_ts": root_created_ts
        })
        
    history_data["seen_ids"] = list(seen_ids)
    history_data["recent_articles"] = recent_articles
    save_history(history_data)
    
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
        
    print("\n(Check file data/seen_articles.json to view memory state)")
