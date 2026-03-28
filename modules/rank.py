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

from modules.state_manager import check_recent_topic
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

def calc_keyword_score(title: str, summary: str) -> Tuple[float, float, float, bool, bool]:
    """
    [V4.8] Tính điểm Keyword Deterministic: 
    Trả về (Positive_Score, Penalty_Score, Token_Modifier, Has_Negative_Event, Has_Noise_Core).
    [V4.8 FIX] Chỉ scan TITLE — summary bị loại khỏi scan keyword/entity.
    Lý do: summary do phóng viên tóm tắt, thường dùng từ mạnh (launch, partner...)
    khiến bài PR/hội nghị vô danh leo lên đầu oan.
    """
    text = title.lower()  # [FIX] Title-only
    
    positive_score = 0.0
    penalty_score = 0.0
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
                          
    search_text = title.lower()  # [FIX] Title-only — tránh entity giả từ summary
    has_standard_core = detect_entities(search_text, standard_core_list)
    has_noise_core = detect_entities(search_text, noise_pool)
    
    has_core_entity = has_standard_core or has_noise_core
    
    # Lấy cấu hình Phạt từ config
    penalty_multiplier = SCORING_WEIGHTS.get("non_core_penalty_multiplier", 0.4)
    exempt_categories = SCORING_WEIGHTS.get("penalty_exempt_categories", ["market_moving", "macro_politics", "urgent"])
    
    # 1. Quét các rổ từ khóa tiêu chuẩn
    # [V4.7] Strict 1-Hit Bucket: Khớp 1 keyword là nhận trọn 100% Base Weight của rổ đo. Thực thi bằng break.
    # [V4.6] Single-Best Bucket: Chỉ giữ lại Rổ có điểm cao nhất.
    best_bucket_score = 0.0

    for cat, base_w in SCORING_WEIGHTS["keyword_caps"].items():
        matched = False
        for k in SCORING_WEIGHTS["keyword_categories"].get(cat, []):
            pattern = r"\b" + re.escape(k) + r"\b"
            if re.search(pattern, text):
                matched = True
                break  # Strict 1-Hit: Thoát vòng lặp ngay lập tức khi tìm thấy 1 keyword.

        if matched:
            if cat == "market_moving":
                has_market_moving = True
            elif cat == "price_analysis":
                has_price_analysis = True
            elif cat == "macro_politics":
                has_macro_politics = True
            elif cat == "negative_event":
                has_negative_event = True

            if base_w > 0:
                current_bucket_score = float(base_w)
                
                # [REFINED V4.8] Asset Tiering
                if cat not in exempt_categories:
                    if not has_core_entity:
                        # Shitcoin/TradFi -> Bị phạt 60% rổ điểm
                        current_bucket_score *= penalty_multiplier
                    # Noise Penalty được chuyển ra ngoài để chia toàn bộ điểm bài báo

                # [V4.6] Chỉ giữ rổ có điểm cao nhất
                best_bucket_score = max(best_bucket_score, current_bucket_score)
            else:
                current_penalty = float(base_w) # base_w là số âm cho rổ phạt
                # Contextual Filter: If Price Analysis matches BUT Market Moving/Macro exists -> Reduce Penalty by 70%
                if cat == "price_analysis" and (has_market_moving or has_macro_politics):
                    current_penalty *= SCORING_WEIGHTS.get("contextual_penalty_multiplier", 0.3)
                penalty_score += current_penalty

    # Cộng điểm từ rổ tốt nhất vào positive_score
    positive_score += best_bucket_score

    # 2. Xóa Compound Tech Regex (Do đã thống nhất đơn giản hóa bằng keywords)

    # 3. Stackable Entity Bonus Module
    token_modifier = 0.0
    
    # Giữ lại hệ thống Phạt mềm cho bài phân tích giá (thầy dùi)
    combined_entities = SCORING_WEIGHTS.get("major_tokens", []) + SCORING_WEIGHTS.get("major_exchanges", [])
    if has_price_analysis and not (has_market_moving or has_negative_event):
        if detect_entities(search_text, combined_entities):
            token_modifier = SCORING_WEIGHTS.get("SPECULATION_SOFT_PENALTY_SCORE", -10.0)
            penalty_score += token_modifier  # Phạt bài thầy dùi

    # [V4.6] Single-Best Entity Bonus: Chỉ lấy điểm entity nhóm CAO NHẤT
    entity_bonuses = SCORING_WEIGHTS.get("entity_bonuses", {})
    entity_bonus_candidates = []
    if detect_entities(search_text, SCORING_WEIGHTS.get("major_tokens", [])):
        entity_bonus_candidates.append(entity_bonuses.get("major_tokens", 3.0))
    if detect_entities(search_text, SCORING_WEIGHTS.get("major_exchanges", [])):
        entity_bonus_candidates.append(entity_bonuses.get("major_exchanges", 2.0))
    if detect_entities(search_text, SCORING_WEIGHTS.get("macro_entities", [])):
        entity_bonus_candidates.append(entity_bonuses.get("macro_entities", 1.0))
    positive_score += max(entity_bonus_candidates) if entity_bonus_candidates else 0.0

    return positive_score, penalty_score, token_modifier, has_negative_event, has_noise_core

def calc_standard_time_decay(published_ts: int, current_ts: int) -> float:
    """Hàm Exponential Time Decay cơ bản."""
    # Nếu published_ts là 0 hoặc trước năm 2020 → fallback về current_ts (decay=1.0)
    MIN_VALID_TS = 1577836800  # 2020-01-01
    if not published_ts or published_ts < MIN_VALID_TS:
        published_ts = current_ts
    hours_passed = (current_ts - published_ts) / 3600.0
    if hours_passed < 0:
        hours_passed = 0
    # [V2 REVERTED] Bỏ cap 48h — nó khiến tất cả bài có TimeDecay=0.19 do root_created_ts cũ.
    # Thay bằng decay floor 0.12 — bài cực kỳ cũ (Bitfinex 2022) vẫn giữ 12% điểm, không về 0.
    lmbda = SCORING_WEIGHTS["time_decay_lambda_per_hour"]
    raw_multiplier = math.exp(-lmbda * hours_passed)
    DECAY_FLOOR = 0.12
    return round(max(raw_multiplier, DECAY_FLOOR), 4)

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
    
    # V4.7: Adaptive Weight và Frequency Tracking đã bị loại bỏ hoàn toàn.
    # 1. Base Score Configuration
    base_score = SCORING_WEIGHTS["base_score"]
    
        
    # 2. Xếp hạng từng bài
    for art in articles:
        text_lower = (art["title"] + " " + art.get("summary", "")).lower()
        
        # [V4.6] Hard Reject đã được bỏ. Lọc tự nhiên qua price_analysis penalty + min_publish_score.
            
        # A. Base Impacts
        positive_kw_score, penalty_kw_score, token_modifier, has_negative_event, has_noise_core = calc_keyword_score(art["title"], art.get("summary", ""))

        # [NEW] Capital Flow Bonus (Tier 2)
        capital_flow_bonus = 0.0
        cf_pattern = SCORING_WEIGHTS.get("CAPITAL_FLOW_REGEX")
        if cf_pattern and re.search(cf_pattern, text_lower):
            capital_flow_bonus = SCORING_WEIGHTS.get("CAPITAL_FLOW_BONUS", 2.0)
            positive_kw_score += capital_flow_bonus
        
        # Thể loại để lấy Topic Fatigue đã bị loại bỏ ở bản V4.7 do tính thiếu công bằng.
        
        # B. Tín nhiệm nguồn
        src_cred = SOURCE_CREDIBILITY.get(art["source_name"], 1.0)
        
        # [NEW] C. Cluster Trend Bonus (Điểm xu hướng báo chí cùng đưa tin)
        cluster_size = art.get("cluster_size", 1)
        trend_bonus = (cluster_size - 1) * SCORING_WEIGHTS.get("cluster_trend_bonus", 2.0)
        
        # [V4.8] Absolute Noise Penalty
        # Nhân chia thẳng tay toàn bộ điểm dương (Base + Rổ + Entity + Capital) nếu có Noise Token
        base_positive = base_score + positive_kw_score
        noise_penalty_applied = 1.0
        if has_noise_core:
            noise_penalty_applied = SCORING_WEIGHTS.get("noise_penalty_multiplier", 0.5)
            base_positive *= noise_penalty_applied

        # D. Editorial Score (Trend Bonus cộng SAU KHI đã chia Noise)
        editorial_score = (base_positive + penalty_kw_score + trend_bonus) * src_cred

        # E. Time Decay (Càng cũ càng giảm)
        # [V4.8 FINAL] Chỉ dùng published_ts (ngày RSS đăng bài).
        # root_created_ts KHÔNG tham gia decay — nó phụ trách narrative/clustering, không phải freshness.
        # Fallback: nếu published_ts không có/không hợp lệ → dùng current_ts (decay=1.0, không phạt).
        MIN_VALID_TS = 1577836800  # 2020-01-01
        _pub_ts = art.get("published_ts") or 0
        effective_ts = _pub_ts if _pub_ts >= MIN_VALID_TS else current_ts
        decay_mult = calc_standard_time_decay(effective_ts, current_ts)
        
        # F. FINAL SCORE formula (V4.1 Trend-Aware)
        total_score = editorial_score * decay_mult
        
        # Enhanced breakdown_log for Rank Debugging
        breakdown_log = (
            f"\n📊 [RANK DEBUG] Article: '{art['title'][:60]}...'\n"
            f"  [+] Base: {base_score:.1f} | Source Cred: {src_cred:.1f} | Trend Bonus: {trend_bonus:+.1f} (Cluster: {cluster_size})\n"
            f"  [+] Kw Bonus: {positive_kw_score - capital_flow_bonus:.2f} | Capital Flow: {capital_flow_bonus:+.1f} | Token Mod: {token_modifier:+.1f}\n"
            f"  [-] Penalty: {penalty_kw_score:.2f}\n"
            f"  [*] Mults: Noise={noise_penalty_applied}x | TimeDecay={decay_mult:.2f}\n"
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
        # Chỉ log INFO cho bài đủ điều kiện đăng (score >= min_publish_score) hoặc negative_event
        # Bài thấp điểm (bài cũ, rác, TechCrunch Disrupt...) hạ xuống DEBUG để không ngập log
        min_log_score = SCORING_WEIGHTS.get("min_publish_score", 5.0)
        if art["score"] >= min_log_score or has_negative_event:
            logger.info(breakdown_log)
        else:
            logger.debug(breakdown_log)
        
    # Lọc bỏ các bài bị Hard Reject (-999.0) khỏi danh sách để tránh lọt vào Selector
    articles = [a for a in articles if a.get("score", 0) > -500.0]
        
    # [V4.7] Keyword logging has been removed
        
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
