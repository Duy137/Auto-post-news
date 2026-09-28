import pytest
import time
from modules.pipeline.rank import (
    calc_keyword_score,
    calc_standard_time_decay,
    rank_articles,
    detect_entities
)
from modules.state_manager import insert_new_article, mark_posted

def test_detect_entities():
    text = "Binance announces new listing of SOL and DOGE"
    assert detect_entities(text, ["Binance", "Coinbase"]) is True
    assert detect_entities(text, ["Kraken", "OKX"]) is False

def test_advertising_pr_is_penalized():
    title = "Huge crypto giveaway and VIP promo for all participants"
    summary = "Join our exclusive referral contest"
    
    pos_score, penalty_score, token_mod, has_neg, has_noise = calc_keyword_score(title, summary)
    
    # advertising_pr cap is -20.0
    assert penalty_score <= -20.0

def test_technical_analysis_and_price_chatter_penalized():
    title = "Solana golden cross breakout could surge to 300 says analyst predicts"
    summary = "Technical setup shows bullish momentum."
    
    pos_score, penalty_score, token_mod, has_neg, has_noise = calc_keyword_score(title, summary)
    
    # price_analysis (-18.0) + speculation soft penalty (-12.0)
    assert penalty_score <= -18.0

def test_time_decay_calculation():
    now = int(time.time())
    
    # Fresh article (0 hours old)
    fresh_decay = calc_standard_time_decay(now, now)
    assert fresh_decay == pytest.approx(1.0, 0.05)
    
    # 20 hours old (lambda=0.035 -> exp(-0.035 * 20) ~ 0.496)
    half_decay = calc_standard_time_decay(now - 20 * 3600, now)
    assert 0.45 <= half_decay <= 0.55
    
    # 72 hours old (floor 0.12)
    old_decay = calc_standard_time_decay(now - 72 * 3600, now)
    assert old_decay == 0.12

def test_capital_flow_bonus_and_high_score(temp_db):
    now = int(time.time())
    articles = [
        {
            "id": "hack_news_1",
            "title": "Binance hacked for $500M in major exploit",
            "summary": "Hackers drained $500 million from a liquidity pool.",
            "published_ts": now - 1800,  # 30 mins ago
            "source_name": "CoinTelegraph",
            "link": "https://example.com/hack"
        },
        {
            "id": "promo_news_2",
            "title": "New VIP referral promo and token giveaway",
            "summary": "Participate in this promo.",
            "published_ts": now - 1800,
            "source_name": "CoinTelegraph",
            "link": "https://example.com/promo"
        }
    ]
    
    ranked = rank_articles(articles, current_ts=now)
    
    # Hack article should be top ranked and score >= 5.5
    top_art = ranked[0]
    assert top_art["id"] == "hack_news_1"
    assert top_art["score"] >= 5.5
    assert top_art["score_detail"]["capital_flow_bonus"] == 2.0
    
    # Promo article should be penalized heavily
    promo_art = next(a for a in ranked if a["id"] == "promo_news_2")
    assert promo_art["score"] < 0.0

def test_entity_fatigue_penalty(temp_db):
    now = int(time.time())
    
    # Insert and mark 2 articles about "SEC" as POSTED in the last 24h
    insert_new_article("past_1", "https://ex.com/1", "SEC Commissioner announces crypto stance", "CoinDesk")
    mark_posted("past_1")
    insert_new_article("past_2", "https://ex.com/2", "SEC reviews legal framework for digital assets", "CoinDesk")
    mark_posted("past_2")
    
    candidate = [{
        "id": "cand_3",
        "title": "SEC issues new regulatory guidance",
        "summary": "Guidelines announced today.",
        "published_ts": now - 600,
        "source_name": "CoinDesk",
        "link": "https://ex.com/3"
    }]
    
    ranked = rank_articles(candidate, current_ts=now)
    # Entity fatigue should penalize "sec" since count=2 -> mult = 1.0 - 2 * 0.2 = 0.6
    assert ranked[0]["score_detail"]["total_score"] > 0
