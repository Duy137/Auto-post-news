import time
import math
import logging
import re
from typing import List, Dict, Any, Tuple

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Article, ScoreDetail
from config import SCORING_WEIGHTS, RSS_SOURCES, ORCHESTRATION_CONFIG

logger = logging.getLogger(__name__)

# Pre-compile source multipliers for O(1) lookup
SOURCE_CREDIBILITY = {s["name"]: s.get("credibility_score", 1.0) for s in RSS_SOURCES}
SOURCE_LATENCY = {s["name"]: s.get("latency_advantage_score", 1.0) for s in RSS_SOURCES}

from modules.state_manager import get_keyword_frequencies_24h, log_keywords, check_recent_topic
from modules.express_fingerprint import extract_fingerprints

def clean_text(text: str) -> str: #Chà nhám văn bản (xóa dấu phẩy, viết thường hết) để chuẩn bị cho việc dò tìm từ khóa.
    """Loại bỏ dấu câu và lowercase text."""
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())

def get_adaptive_keyword_weight(keyword: str, base_weight: float, kw_freqs: Dict[str, int]) -> float:
    # Lấy freq thực tế trong 24h, nếu không có thì lấy baseline cấy sẵn.
    freq = kw_freqs.get(keyword)
    if freq is None:
        freq = SCORING_WEIGHTS["baseline_keyword_freqs"].get(keyword, 1.0)
    
    # Phạt log: 1 / log10(freq + 10) 
    penalty = 1.0 / math.log10(freq + 10)
    return base_weight * penalty

def calc_adaptive_keyword_score(title: str, summary: str, kw_freqs: Dict[str, int]) -> Tuple[float, float, List[str]]:
    """Tính Keyword Score adaptive bằng Regex Boundary. Trả về (Positive_Score, Penalty_Score, List_Words)."""
    text = f"{title} {summary}".lower()
    
    positive_score = 0.0
    penalty_score = 0.0
    found_keywords = []
    
    # 1. Quét các rổ từ khóa tiêu chuẩn
    for cat, base_w in SCORING_WEIGHTS["keyword_caps"].items():
        cat_score = 0.0
        for k in SCORING_WEIGHTS["keyword_categories"].get(cat, []):
            # Dùng regex word boundary để tránh nhận diện sai (ví dụ: "price.analysis" hay "priced")
            pattern = r"\b" + re.escape(k) + r"\b"
            if re.search(pattern, text):
                w = get_adaptive_keyword_weight(k, abs(base_w), kw_freqs)
                # Tích lũy điểm trong rổ
                if base_w > 0:
                    cat_score += w
                else:
                    cat_score -= w # Trừ điểm mềm (Penalty)
                found_keywords.append(k)
        
        # Áp dụng Giới hạn Trần (Cap) cho từng rổ để tránh lạm phát
        if base_w > 0:
            positive_score += min(cat_score, base_w)
        else:
            penalty_score += max(cat_score, base_w) # base_w là số âm (vd: -6.0)

    # 2. Quét Compound Tech Regexes (Công nghệ Tài sản lõi)
    compound_weight = SCORING_WEIGHTS.get("compound_tech_weight", 5.0)
    for pattern in SCORING_WEIGHTS.get("compound_tech_regexes", []):
        if re.search(pattern, text):
            positive_score += compound_weight
            found_keywords.append(f"TECH_COMPOUND_MATCH")
            break # Chỉ thưởng 1 lần cho cụm công nghệ để tránh lạm phát

    return positive_score, penalty_score, found_keywords

def calc_editorial_verb_score(title: str) -> float:
    """Lấy điểm trọng số cộng dồn của các động từ hành động Vĩ mô."""
    text = title.lower()
    total_verb_score = 0.0
    verb_cap = 4.0 # Giới hạn tối đa cho nhóm Động từ
    
    for verb, weight in SCORING_WEIGHTS["editorial_verbs"].items():
        pattern = r"\b" + re.escape(verb) + r"\b"
        if re.search(pattern, text):
            total_verb_score += weight
            
    return min(total_verb_score, verb_cap)

SHOCK_VERBS = {"halt", "exploit", "breach", "emergency", "freeze", "fbi", "raid", "bankruptcy", "bankrupt"}

def calc_shock_score(title: str, summary: str, kw_freqs: Dict[str, int]) -> float:
    """Săn Anomalies, Extreme verbs & Cú vọt Frequency."""
    score = 0.0
    text = clean_text(title + " " + summary)
    words = set(text.split())
    
    if any(v in words for v in SHOCK_VERBS):
        score += 0.3
        
    for w in words:
        if len(w) > 4:
            baseline = SCORING_WEIGHTS["baseline_keyword_freqs"].get(w)
            current = kw_freqs.get(w, 0)
            if baseline and current > baseline * 5:
                score += 0.2
                break
    return score

def calc_bounded_viral_potential(raw: float) -> float:
    """Sigmoid Normalization khóa khung điểm (0.7 -> 1.8)."""
    return round(0.7 + 1.1 / (1.0 + math.exp(-(raw - 0.98))), 4)

def calc_directional_time_decay(published_ts: int, current_ts: int, momentum_delta: float) -> float:
    """Hàm Exponential Time Decay có xét Momentum Directionality."""
    hours_passed = (current_ts - published_ts) / 3600.0
    if hours_passed < 0:
        hours_passed = 0
        
    lmbda = SCORING_WEIGHTS["time_decay_lambda_per_hour"]
    
    # Điều chỉnh decay rate theo chênh lệch Momentum
    if momentum_delta > 0:
        lmbda = max(0.01, lmbda - 0.02 * momentum_delta)
    elif momentum_delta < 0:
        lmbda = min(0.15, lmbda + 0.05 * abs(momentum_delta))
        
    multiplier = math.exp(-lmbda * hours_passed)
    return round(multiplier, 4)

def detect_cross_source_momentum(articles: List[Article]) -> Dict[str, bool]: #Kỹ thuật phát hiện Trend. Nếu có 2 bài báo đến từ 2 nguồn khác nhau nhưng lại nói chung 1 cụm từ khóa y hệt nhau, nó bật cờ "Sức nóng dư luận" (Momentum) = True cho cả 2 bài.
    """
    Detect các bài viết đang được nhiều nguồn nhắc tới (Jaccard > 0.45).
    Trả về Dict: {article_id: có_momentum_hay_khong}
    (Phiên bản O(N^2) thu nhỏ - vì số lượng bài lúc này (sau deduplicate) đã rất ít ~20 bài).
    """
    from modules.deduplicator import get_article_tokens, calculate_jaccard_similarity, SIMILARITY_THRESHOLD
    
    N = len(articles)
    has_momentum = {a["id"]: False for a in articles}
    
    # Tokenize sẵn
    tokens_map = {a["id"]: get_article_tokens(a["title"], a["link"]) for a in articles}
    
    for i in range(N):
        art_i = articles[i]
        for j in range(i + 1, N):
            art_j = articles[j]
            # Nếu 2 báo KHÁC NHAU cùng viết 1 chủ đề
            if art_i["source_name"] != art_j["source_name"]:
                sim = calculate_jaccard_similarity(tokens_map[art_i["id"]], tokens_map[art_j["id"]])
                if sim >= SIMILARITY_THRESHOLD:
                    has_momentum[art_i["id"]] = True
                    has_momentum[art_j["id"]] = True
                    
    return has_momentum

def rank_articles(articles: List[Article], current_ts: int = None) -> List[Article]: #Nhạc trưởng của Khâu 3. Nó gom tất cả các hàm trên lại, gõ máy tính theo đúng công thức: Total = (Base + Tương Tác Chữ + Momentum) * Uy Tín * Thối Rữa Thời Gian.
    """
    Main Phase 3 Ranking Function. 
    Total Score = (Base + KeywordCap + VerbBoost + MomentumBoost) * SourceP * TimeDecay * TopicNovelty (TopicPenalty làm ở Phase 4)
    """
    if not articles:
        return []
        
    if current_ts is None:
        current_ts = int(time.time())
        
    logger.info(f"Scoring {len(articles)} articles...")
    
    kw_freqs = get_keyword_frequencies_24h()
    keywords_to_log = []
    
    # [NEW] Regex Pattern để diệt gọn bài phân tích giá / rác đầu cơ
    SPECULATION_REJECT_PATTERN = r"(price\s+target|price\s+prediction|technical\s+analysis|bullish|bearish|support\s+level|resistance\s+level|analyst\s+predicts?|forecast\s+price)"
    
    # 1. Tính toán Cross-Source Momentum (Global view của mảng đợt này)
    momentum_map = detect_cross_source_momentum(articles)
    base_score = SCORING_WEIGHTS["base_score"]
    boost_val = SCORING_WEIGHTS["cross_source_momentum_score"]
    
    from config import ADAPTIVE_FATIGUE_WINDOWS
    
    # 2. Xếp hạng từng bài
    for art in articles:
        text_lower = (art["title"] + " " + art.get("summary", "")).lower()
        
        # [NEW] HARD REJECT: Kiểm tra mẫu Câu Đầu Cơ Giá
        speculation_match = re.search(SPECULATION_REJECT_PATTERN, text_lower)
        if speculation_match:
            logger.warning(f"🛑 [FILTERED] Article '{art['id']}': Hard dropped due to Speculation Pattern Detected: '{speculation_match.group(1)}'")
            art["score"] = -999.0
            art["score_detail"] = {"error": "Speculation Hard Reject"}
            continue # Vứt bài này ngay lập tức, không tốn CPU tính điểm nữa
            
        # A. Base Impacts
        positive_kw_score, penalty_kw_score, words_found = calc_adaptive_keyword_score(art["title"], art.get("summary", ""), kw_freqs)
        kw_score = positive_kw_score + penalty_kw_score # kw_score nay chứa cả thưởng và phạt (đã cap)
        keywords_to_log.extend(words_found)
        
        verb_score = calc_editorial_verb_score(art["title"])
        
        # B. Tín hiệu lan truyền
        shock_score = calc_shock_score(art["title"], art.get("summary", ""), kw_freqs)
        
        momentum_score = boost_val if momentum_map.get(art["id"]) else 0.0
        cluster_size = art.get("cluster_size", 1)
        momentum_delta = cluster_size - 1.5 
        
        # Thể loại để lấy Topic Fatigue
        entity_type = "default"
        text_lower = (art["title"]+art.get("summary", "")).lower()
        if shock_score > 0: entity_type = "hack"
        elif "etf" in text_lower: entity_type = "etf"
        elif "sec" in text_lower: entity_type = "sec"
        
        window = ADAPTIVE_FATIGUE_WINDOWS.get(entity_type, 72)
        root_age_hours = (current_ts - art.get("root_created_ts", art.get("published_ts", current_ts))) / 3600.0
        fatigue_penalty = -0.5 if root_age_hours > window else 0.0
        
        # C. Uy tín & Độ trễ
        src_cred = SOURCE_CREDIBILITY.get(art["source_name"], 1.0)
        src_latency = SOURCE_LATENCY.get(art["source_name"], 1.0)
        authority_viral_impact = min(0.3, src_latency - 1.0) # Khóa quyền lực Authority <= 30% trong Viral
        
        # D. Viral Potential
        raw_viral = momentum_score + shock_score + fatigue_penalty + authority_viral_impact
        viral_potential = calc_bounded_viral_potential(raw_viral)

        # E. Editorial Score
        editorial_score = (base_score + kw_score + verb_score) * src_cred

        # F. Decay
        decay_mult = calc_directional_time_decay(art.get("root_created_ts", art.get("published_ts", current_ts)), current_ts, momentum_delta)
        
        # G. FINAL SCORE formula (V3.0 Deterministic)
        total_score = editorial_score * viral_potential * decay_mult
        
        # [NEW] Tích hợp chi tiết breakdown_log để in ra Console cho dễ debug
        breakdown_log = (
            f"\n📊 [RANKING] Article '{art['title'][:40]}...':\n"
            f"  - MACRO/TECH_SCORE (+): {positive_kw_score:.2f} (Keywords: {words_found})\n"
            f"  - EDITORIAL_SCORE  (+): {verb_score:.2f}\n"
            f"  - PENALTY          (-): {penalty_kw_score:.2f}\n"
            f"  - VIRAL/SHOCK_MULT (x): {viral_potential:.2f} (Shock:{shock_score:.1f}, Momentum:{momentum_score:.1f})\n"
            f"  - DECAY_MULT       (x): {decay_mult:.2f}\n"
            f"  - SOURCE_CRED      (x): {src_cred:.2f}\n"
        )
        
        # Phase 7: RSS Cooldown Suppression Guard
        # Extract vân tay từ tựa đề RSS. Nếu trùng topic vừa đăng trên Telegram/RSS trong 60 phút qua -> Phạt điểm.
        rss_fingerprints = extract_fingerprints(art["title"])
        topic_novelty_multiplier = 1.0
        
        if rss_fingerprints:
            fingerprint_signature = "||".join(rss_fingerprints)
            # Check DB cờ chung (recent_topics)
            window_minutes = ORCHESTRATION_CONFIG.get("fingerprint_window_minutes", 60)
            if check_recent_topic(fingerprint_signature, minutes=window_minutes):
                topic_novelty_multiplier = ORCHESTRATION_CONFIG.get("rss_penalty_multiplier", 0.1)
                logger.warning(f"📉 [RSS SUPPRESSION] Article '{art['id']}' matches recent topic '{fingerprint_signature}'. Applying {topic_novelty_multiplier}x penalty.")
                total_score *= topic_novelty_multiplier
                
        # Điền Score Detail
        art["score_detail"] = {
            "base_score": base_score,
            "positive_keyword_score": round(positive_kw_score, 2),
            "penalty_keyword_score": round(penalty_kw_score, 2),
            "editorial_verb_score": verb_score,
            "cross_source_momentum_score": momentum_score,
            "source_credibility": src_cred,
            "source_latency_advantage": src_latency,
            "shock_score": round(shock_score, 2),
            "viral_potential": round(viral_potential, 2),
            "editorial_score": round(editorial_score, 2),
            "topic_novelty_multiplier": topic_novelty_multiplier, 
            "time_decay_multiplier": decay_mult,
            "total_score": round(total_score, 2)
        }
        art["score"] = art["score_detail"]["total_score"]
        
        # Bổ sung dòng Total Score vào Breakdown Log và in ra Console
        breakdown_log += f"  => FINAL_SCORE    : {art['score']:.2f}\n"
        if art["score"] > 8.0: # Chỉ in log chi tiết các bài khá khẩm để tránh rác console
            logger.info(breakdown_log)
        
    # Lọc bỏ các bài bị Hard Reject (-999.0) khỏi danh sách để tránh lọt vào Selector
    articles = [a for a in articles if a.get("score", 0) > -500.0]
        
    # Log keywords for future weighting
    if keywords_to_log:
        log_keywords(list(set(keywords_to_log)))
        
    # Sort DESC output (Tiện cho việc nhìn log)
    articles.sort(key=lambda x: x["score"], reverse=True)
    return articles

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    print("\n[MÔ PHỎNG PHASE 3: RANKING ENGINE]")
    
    # Tụi mình đóng vai các nhà báo :D
    now = int(time.time())
    
    mock_articles: List[Article] = [
        # Tin 1: Tin mới nổ, báo xịn, cực hot
        {
            "id": "1", "title": "SEC officially approves Bitcoin ETF", "link": "link1", "raw_source_url": "", 
            "summary": "Massive win for crypto.", 
            "published_ts": now - 3600, # 1h trước
            "source_name": "CoinTelegraph", "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 2: Cùng chủ đề Tin 1, nhưng từ báo dỏm, ra trễ hơn xíu -> Momentum Boost kích hoạt cho cả 2.
        {
            "id": "2", "title": "SEC approves BTC ETF today", "link": "link2", "raw_source_url": "", 
            "summary": "", 
            "published_ts": now - 7200, # 2h trước
            "source_name": "UnknownBlog", "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 3: Tin hack khẩn cấp, cực nóng, nhưng từ cách đây 2 ngày (quá cũ)
        {
            "id": "3", "title": "Binance hacked for $500M", "link": "link3", "raw_source_url": "", 
            "summary": "Biggest hack in history.", 
            "published_ts": now - (48 * 3600), # 48h trước -> Decay sẽ làm nó chết!
            "source_name": "CoinTelegraph", "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 4: Tin bình luận lôm côm từ báo xịn (Không có Event Verbs)
        {
            "id": "4", "title": "Why we think the bull run is near", "link": "link4", "raw_source_url": "", 
            "summary": "Opinion piece.", 
            "published_ts": now - 1800, # Vừa đăng xong
            "source_name": "CoinTelegraph", "score": None, "score_detail": None, "tweet_content": None
        }
    ]
    
    ranked = rank_articles(mock_articles, current_ts=now)
    
    import json
    for rank, a in enumerate(ranked):
        print(f"\n#{rank+1} [Điểm: {a['score']}] - {a['title']}")
        print(f"  Source: {a['source_name']} | Tuổi: {(now - a['published_ts'])//3600}h")
        print(f"  Explain: {json.dumps(a['score_detail'])}")
