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

def detect_entities(text: str, entity_list: List[str]) -> bool:
    """Detect presence of major tokens or exchanges using word boundaries."""
    text_lower = text.lower()
    for entity in entity_list:
        # Avoid matching substrings like "dot" in "polkadot" accidentally, though entity_list should be distinct.
        pattern = r"\b" + re.escape(entity.lower()) + r"\b"
        if re.search(pattern, text_lower):
            return True
    return False

def get_adaptive_keyword_weight(keyword: str, base_weight: float, kw_freqs: Dict[str, int]) -> float:
    # Lấy freq thực tế trong 24h, nếu không có thì lấy baseline cấy sẵn.
    freq = kw_freqs.get(keyword)
    if freq is None:
        freq = SCORING_WEIGHTS["baseline_keyword_freqs"].get(keyword, 1.0)
    
    # Phạt log: 1 / log10(freq + 10) 
    penalty = 1.0 / math.log10(freq + 10)
    return base_weight * penalty

def calc_adaptive_keyword_score(title: str, summary: str, kw_freqs: Dict[str, int]) -> Tuple[float, float, List[str], float, bool]:
    """Tính Keyword Score adaptive bằng Regex Boundary. Trả về (Positive_Score, Penalty_Score, List_Words, Token_Modifier, Has_Priority_Event)."""
    text = f"{title} {summary}".lower()
    
    positive_score = 0.0
    penalty_score = 0.0
    found_keywords = []
    has_market_moving = False
    has_macro_politics = False
    has_price_analysis = False
    has_negative_event = False
    
    # [REFINED V4.4] Asset Tiering Penalty - Phân tách Token Chuẩn và Token Nhiễu
    noise_pool = SCORING_WEIGHTS.get("noise_tokens", ["bitcoin", "btc", "ethereum", "eth"])
    raw_major = SCORING_WEIGHTS.get("major_tokens", [])
    standard_tokens = [t for t in raw_major if t.lower() not in [n.lower() for n in noise_pool]]
    
    standard_core_list = (standard_tokens + 
                          SCORING_WEIGHTS.get("macro_entities", []) + 
                          SCORING_WEIGHTS.get("major_exchanges", []))
                          
    search_text = f"{title} {summary}".lower()
    has_standard_core = detect_entities(search_text, standard_core_list)
    has_noise_core = detect_entities(search_text, noise_pool)
    
    has_core_entity = has_standard_core or has_noise_core
    
    # Lấy cấu hình Phạt từ config
    penalty_multiplier = SCORING_WEIGHTS.get("non_core_penalty_multiplier", 0.4)
    exempt_categories = SCORING_WEIGHTS.get("penalty_exempt_categories", ["market_moving", "macro_politics", "urgent"])
    
    # 1. Quét các rổ từ khóa tiêu chuẩn
    for cat, base_w in SCORING_WEIGHTS["keyword_caps"].items():
        cat_score = 0.0
        for k in SCORING_WEIGHTS["keyword_categories"].get(cat, []):
            pattern = r"\b" + re.escape(k) + r"\b"
            if re.search(pattern, text):
                w = get_adaptive_keyword_weight(k, abs(base_w), kw_freqs)
                if base_w > 0:
                    cat_score += w
                else:
                    cat_score -= w # Soft Penalty
                found_keywords.append(k)
                
                if cat == "market_moving":
                    has_market_moving = True
                elif cat == "price_analysis":
                    has_price_analysis = True
                elif cat == "macro_politics":
                    has_macro_politics = True
                elif cat == "negative_event":
                    has_negative_event = True
        
        # Áp dụng Giới hạn Trần (Cap) cho từng rổ
        if base_w > 0:
            current_bucket_score = min(cat_score, base_w)
            
            # [REFINED V4.4] Asset Tiering 
            if cat not in exempt_categories:
                if not has_core_entity:
                    # Shitcoin/TradFi -> Bị phạt 60% rổ điểm
                    current_bucket_score *= penalty_multiplier
                elif has_noise_core and not has_standard_core:
                    # Chỉ có mặt Ultra-Noise Tokens (Bitcoin) -> Bị phạt 30% để chống Spam SEO
                    noise_multi = SCORING_WEIGHTS.get("noise_penalty_multiplier", 0.7)
                    current_bucket_score *= noise_multi
                # Nếu có standard_core (Thuần Altcoins/Exchanges/Macro) -> Giữ nguyên 100% điểm
                
            positive_score += current_bucket_score
        else:
            current_penalty = max(cat_score, base_w)
            # Contextual Filter: If Price Analysis matches BUT Market Moving/Macro exists -> Reduce Penalty by 70%
            if cat == "price_analysis" and (has_market_moving or has_macro_politics):
                current_penalty *= 0.3
            penalty_score += current_penalty

    # 2. Xóa Compound Tech Regex (Do đã thống nhất đơn giản hóa bằng keywords)

    # 3. Token-Aware Scoring Module
    token_modifier = 0.0
    combined_entities = SCORING_WEIGHTS.get("major_tokens", []) + SCORING_WEIGHTS.get("major_exchanges", [])
    if detect_entities(f"{title} {summary}", combined_entities):
        if has_price_analysis and not (has_market_moving or has_negative_event):
            token_modifier = SCORING_WEIGHTS.get("SPECULATION_SOFT_PENALTY_SCORE", -10.0)
            penalty_score += token_modifier  # Phạt cực nặng bài thầy dùi
        elif has_market_moving or has_negative_event:
            token_modifier = 2.0
            positive_score += token_modifier # Thưởng nhẹ để đôn rank bài tin tức thực sự

    return positive_score, penalty_score, found_keywords, token_modifier, has_negative_event

def calc_standard_time_decay(published_ts: int, current_ts: int) -> float:
    """Hàm Exponential Time Decay cơ bản."""
    hours_passed = (current_ts - published_ts) / 3600.0
    if hours_passed < 0:
        hours_passed = 0
        
    lmbda = SCORING_WEIGHTS["time_decay_lambda_per_hour"]
    multiplier = math.exp(-lmbda * hours_passed)
    return round(multiplier, 4)

def rank_articles(articles: List[Article], current_ts: int = None) -> List[Article]: #Nhạc trưởng của Khâu 3. Nó gom tất cả các hàm trên lại, gõ máy tính theo đúng công thức: Total = Editorial_Score * TimeDecay * TopicNovelty.
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
    # 1. Base Score Configuration
    base_score = SCORING_WEIGHTS["base_score"]
    
    from config import ADAPTIVE_FATIGUE_WINDOWS
    
    # 2. Xếp hạng từng bài
    for art in articles:
        text_lower = (art["title"] + " " + art.get("summary", "")).lower()
        
        # [MODIFIED] Two-Layer Speculation Filter: Hard Reject
        spec_hard_pattern = SCORING_WEIGHTS.get("SPECULATION_HARD_REJECT_PATTERN", r"price\s+prediction")
        speculation_match = re.search(spec_hard_pattern, text_lower)
        if speculation_match:
            logger.warning(f"🛑 [FILTERED] Article '{art['id']}': Hard dropped due to Speculation Pattern Detected: '{speculation_match.group(0)}'")
            art["score"] = -999.0
            art["score_detail"] = {"error": "Speculation Hard Reject"}
            continue 
            
        # A. Base Impacts
        positive_kw_score, penalty_kw_score, words_found, token_modifier, has_negative_event = calc_adaptive_keyword_score(art["title"], art.get("summary", ""), kw_freqs)
        keywords_to_log.extend(words_found)

        # [NEW] Capital Flow Bonus (Tier 2)
        capital_flow_bonus = 0.0
        cf_pattern = SCORING_WEIGHTS.get("CAPITAL_FLOW_REGEX")
        if cf_pattern and re.search(cf_pattern, text_lower):
            capital_flow_bonus = SCORING_WEIGHTS.get("CAPITAL_FLOW_BONUS", 4.0)
            positive_kw_score += capital_flow_bonus
        
        # Thể loại để lấy Topic Fatigue
        entity_type = "default"
        if has_negative_event: entity_type = "hack"
        elif "etf" in text_lower: entity_type = "etf"
        elif "sec" in text_lower: entity_type = "sec"
        
        window = ADAPTIVE_FATIGUE_WINDOWS.get(entity_type, 72)
        root_age_hours = (current_ts - art.get("root_created_ts", art.get("published_ts", current_ts))) / 3600.0
        fatigue_penalty = -0.5 if root_age_hours > window else 0.0
        
        # B. Tín nhiệm nguồn
        src_cred = SOURCE_CREDIBILITY.get(art["source_name"], 1.0)
        
        # [NEW] C. Cluster Trend Bonus (Điểm xu hướng báo chí cùng đưa tin)
        cluster_size = art.get("cluster_size", 1)
        trend_bonus = (cluster_size - 1) * SCORING_WEIGHTS.get("cluster_trend_bonus", 2.0)
        
        # D. Editorial Score
        editorial_score = (base_score + positive_kw_score + penalty_kw_score + fatigue_penalty + trend_bonus) * src_cred

        # E. Time Decay (Càng cũ càng giảm)
        decay_mult = calc_standard_time_decay(art.get("root_created_ts", art.get("published_ts", current_ts)), current_ts)
        
        # F. FINAL SCORE formula (V4.1 Trend-Aware)
        total_score = editorial_score * decay_mult
        
        # Enhanced breakdown_log for Rank Debugging
        breakdown_log = (
            f"\n📊 [RANK DEBUG] Article: '{art['title'][:60]}...'\n"
            f"  [+] Base: {base_score:.1f} | Source Cred: {src_cred:.1f} | Trend Bonus: {trend_bonus:+.1f} (Cluster: {cluster_size})\n"
            f"  [+] Kw Bonus: {positive_kw_score - capital_flow_bonus:.2f} | Capital Flow: {capital_flow_bonus:+.1f} | Token Mod: {token_modifier:+.1f}\n"
            f"  [-] Penalty: {penalty_kw_score:.2f} | Fatigue: {fatigue_penalty:.1f}\n"
            f"  [*] Mults: TimeDecay={decay_mult:.2f}\n"
            f"  [*] Keywords Found: {list(set(words_found))}\n"
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
            "token_modifier": token_modifier,
            "capital_flow_bonus": capital_flow_bonus,
            "trend_bonus": trend_bonus,
            "editorial_score": round(editorial_score, 2),
            "topic_novelty_multiplier": topic_novelty_multiplier, 
            "total_score": round(total_score, 2)
        }
        art["score"] = art["score_detail"]["total_score"]
        
        # Bổ sung dòng Total Score vào Breakdown Log và in ra Console
        breakdown_log += f"  => FINAL_SCORE    : {art['score']:.2f}\n"
        if art["score"] > 8.0 or has_negative_event: # Chỉ in log chi tiết các bài khá khẩm để tránh rác console
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
    print("\n[RANKING ENGINE SIMULATION]")
    
    # Tụi mình đóng vai các nhà báo :D
    now = int(time.time())
    
    mock_articles: List[Article] = [
        # Tin 1: Tin mới nổ, báo xịn, cực hot, có Token (OKX) + Hành động đầu tư ($100M)
        {
            "id": "1", "title": "OKX receives $100M investment from top venture fund", "link": "link1", "raw_source_url": "", 
            "summary": "Major funding round for the exchange.", 
            "published_ts": now - 3600, # 1h trước
            "source_name": "CoinTelegraph", "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 2: Mẫu thầy dùi, có điểm trừ nặng.
        {
            "id": "2", "title": "Solana could reach $500 next month, analyst predicts", "link": "link2", "raw_source_url": "", 
            "summary": "SOL price prediction is bullish for Q4.", 
            "published_ts": now - 3600, # 1h trước
            "source_name": "CoinDesk", "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 3: Tin hack khẩn cấp, cực nóng, nhưng từ cách đây 2 ngày (quá cũ)
        {
            "id": "3", "title": "Binance hacked for $500M", "link": "link3", "raw_source_url": "", 
            "summary": "Biggest hack in history.", 
            "published_ts": now - (48 * 3600), # 48h trước -> Decay sẽ làm nó chết!
            "source_name": "CoinTelegraph", "score": None, "score_detail": None, "tweet_content": None
        },
        # Tin 4: Tin bình thị trường vô thưởng vô phạt (Không có Event Verbs cũng không dự đoán giá gắt)
        {
            "id": "4", "title": "Bitcoin continues to lead the market rally", "link": "link4", "raw_source_url": "", 
            "summary": "Market shows signs of recovery.", 
            "published_ts": now - 1800, # Vừa đăng xong
            "source_name": "CoinTelegraph", "score": None, "score_detail": None, "tweet_content": None
        }
    ]
    
    ranked = rank_articles(mock_articles, current_ts=now)
    
    import json
    for rank, a in enumerate(ranked):
        print(f"\n#{rank+1} [Score: {a['score']}] - {a['title']}")
        print(f"  Source: {a['source_name']} | Age: {(now - a['published_ts'])//3600}h")
        detail_str = json.dumps(a['score_detail'])
        print(f"  Explain: {detail_str[:150]}..." if len(detail_str) > 150 else f"  Explain: {detail_str}")
