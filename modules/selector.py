import logging
import copy
from typing import List

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Article
from config import SCORING_WEIGHTS
from modules.deduplicator import get_article_tokens, calculate_jaccard_similarity, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

def is_similar_topic(art1: Article, art2: Article) -> bool:
    """Kiểm tra 2 bài viết có dùng chung topic không (dựa trên Jaccard Similarity của tokens)."""
    tokens1 = get_article_tokens(art1["title"], art1["link"])
    tokens2 = get_article_tokens(art2["title"], art2["link"])
    
    sim = calculate_jaccard_similarity(tokens1, tokens2)
    return sim >= SIMILARITY_THRESHOLD

def select_top_articles(ranked_articles: List[Article], top_n: int = 3) -> List[Article]:
    """
    Main Phase 4 Selection Pipeline.
    Nhận mảng bài viết (đã được rank.py chấm điểm và sắp xếp sơ bộ).
    Loại bỏ các bài trùng chủ đề để đảm bảo Newsfeed luôn đa dạng.
    """
    if not ranked_articles:
        return []

    # Bỏ qua các bài báo dưới điểm sàn
    min_score = SCORING_WEIGHTS.get("min_publish_score", 4.0)
    qualified_articles = [art for art in ranked_articles if (art.get("score") or 0) >= min_score]
    
    if not qualified_articles:
        logger.info(f"All {len(ranked_articles)} articles scored below minimum publish threshold ({min_score}). Skipping publishing.")
        return []

    # Sort DESC theo điểm hiện có từ Phase 3 (Đề phòng list đầu vào bị lệch)
    sorted_articles = sorted(qualified_articles, key=lambda x: x["score"] if x["score"] else 0, reverse=True)
    
    selected: List[Article] = []
    penalty_val = SCORING_WEIGHTS["topic_novelty_penalty"]
    
    # Duyệt từ bài cao điểm nhất xuống thấp
    while sorted_articles and len(selected) < top_n:
        # Ppop bài cao điểm nhất vòng hiện tại
        candidate = sorted_articles.pop(0)
        
        # Kiểm tra Diversity: Bài này có trùng chủ đề với bất kỳ bài nào ĐÃ ĐƯỢC CHỌN TRƯỚC ĐÓ không?
        is_novel = True
        for sel_art in selected:
            if is_similar_topic(candidate, sel_art):
                logger.info(f"Penalty Applied! Cùng chủ đề với bài top trên:")
                logger.info(f" - Top: {sel_art['title']}")
                logger.info(f" - Bị phạt: {candidate['title']}")
                is_novel = False
                break
                
        if is_novel:
            # Bài viết chủ đề mới -> An toàn đẩy vào danh sách chọn
            # Cập nhật topic_novelty_multiplier = 1.0 (Giữ nguyên điểm)
            if candidate.get("score_detail"):
                candidate["score_detail"]["topic_novelty_multiplier"] = 1.0
            selected.append(candidate)
        else:
            # Bị trùng chủ đề -> Ép Penalty
            # Thay vì vứt bỏ bài (Hard Drop), thuật toán mềm dẻo sẽ trừ điểm cực mạnh theo Penalty Config
            if candidate.get("score_detail"):
                old_score = candidate["score"]
                
                candidate["score_detail"]["topic_novelty_multiplier"] = penalty_val
                # Recalculate Total Score bằng cách lấy Total Impact * Multipliers
                total_impact = (
                    candidate["score_detail"]["base_score"] +
                    candidate["score_detail"]["keyword_cap_score"] +
                    candidate["score_detail"]["editorial_verb_score"] +
                    candidate["score_detail"]["cross_source_momentum_score"]
                )
                
                new_score = (
                    total_impact * 
                    candidate["score_detail"]["source_multiplier"] * 
                    candidate["score_detail"]["time_decay_multiplier"] * 
                    penalty_val
                )
                
                candidate["score_detail"]["total_score"] = round(new_score, 2)
                candidate["score"] = candidate["score_detail"]["total_score"]
                
                logger.debug(f" -> Điểm rớt từ {old_score} xuống {candidate['score']}")
                
            # Đẩy ngược lại candidate vào pool và resort lại (Re-rank)
            # Rất có thể sau khi bị phạt, nó sẽ rớt thẳng xuống đáy, nhường slot cho bài Top 3 khác môn phái len lên Top 2
            sorted_articles.append(candidate)
            sorted_articles = sorted(sorted_articles, key=lambda x: x["score"] if x["score"] else 0, reverse=True)
            
    logger.info(f"Phase 4 Complete: Selected {len(selected)} articles for tweeting.")
    return selected

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    print("\n[MÔ PHỎNG PHASE 4: SELECTION ENGINE (DIVERSITY CHECK)]\n")
    
    # Mảng Input: Đã được chấm điểm xong từ Phase 3
    mock_ranked: List[Article] = [
        {
            "id": "1", "title": "SEC approves Ethereum ETF", "link": "link1", "raw_source_url": "", 
            "summary": "", "published_ts": 123, "source_name": "CoinTelegraph",
            "score": 25.0, 
            "score_detail": {"base_score": 10.0, "keyword_cap_score": 5.0, "editorial_verb_score": 3.0, "cross_source_momentum_score": 0.0, "source_multiplier": 1.5, "topic_novelty_multiplier": 1.0, "time_decay_multiplier": 0.9, "total_score": 25.0},
            "tweet_content": None
        },
        # Bài số 2 có điểm cực cao (Top 2), nhưng Trùng 90% Keyword với bài Top 1.
        {
            "id": "2", "title": "Ethereum ETF officially approved by SEC", "link": "link2", "raw_source_url": "", 
            "summary": "", "published_ts": 124, "source_name": "TechCrunch", 
            "score": 24.5, 
            "score_detail": {"base_score": 10.0, "keyword_cap_score": 5.0, "editorial_verb_score": 3.0, "cross_source_momentum_score": 0.0, "source_multiplier": 1.5, "topic_novelty_multiplier": 1.0, "time_decay_multiplier": 0.9, "total_score": 24.5},
            "tweet_content": None
        },
        # Bài số 3 điểm thấp hơn một chút, nhưng khác hoàn toàn môn phái (Chủ đề Hack)
        {
            "id": "3", "title": "Solana bridge hacked for $100M", "link": "link3", "raw_source_url": "", 
            "summary": "", "published_ts": 125, "source_name": "UnknownBlog",
            "score": 18.0, 
            "score_detail": {"base_score": 10.0, "keyword_cap_score": 10.0, "editorial_verb_score": 3.0, "cross_source_momentum_score": 0.0, "source_multiplier": 1.0, "topic_novelty_multiplier": 1.0, "time_decay_multiplier": 0.8, "total_score": 18.0},
            "tweet_content": None
        }
    ]
    
    print("--- RANKED INPUT (PHASE 3 OUTPUT) ---")
    for a in mock_ranked:
        print(f"[{a['score']}] {a['title']}")
        
    print("\n--- PROCESSING SELECTION ---")
    results = select_top_articles(mock_ranked, top_n=2)
    
    print("\n--- FINAL SELECTED ARTICLES (PHASE 4 OUTPUT) ---")
    import json
    for rank, a in enumerate(results):
        print(f"\n#{rank+1} [Điểm: {a['score']}] - {a['title']}")
        print(f"  Explain: {json.dumps(a['score_detail'])}")
