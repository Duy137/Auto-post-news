import pytest
import time
import json
import sqlite3
import modules.state_manager as sm
from modules.state_manager import (
    ArticleState,
    insert_new_article,
    claim_next_article,
    transition_state,
    release_processing_timeout,
    insert_to_publish_queue,
    pick_best_from_queue,
    get_best_selected_article,
    mark_queue_published,
    is_event_published,
    mark_event_published,
    check_recent_topic,
    insert_recent_topic,
    check_and_insert_express_seen
)

def test_insert_article_and_unique_constraint(temp_db):
    ok1 = insert_new_article("art_1", "https://site.com/art1", "Title 1", "SourceA")
    assert ok1 is True
    
    # Duplicate ID or duplicate URL should fail
    ok2 = insert_new_article("art_1", "https://site.com/diff", "Title 2", "SourceA")
    assert ok2 is False
    
    ok3 = insert_new_article("art_2", "https://site.com/art1", "Title 3", "SourceA")
    assert ok3 is False

def test_atomic_claim_and_transition(temp_db):
    insert_new_article("art_1", "https://site.com/art1", "Title 1", "SourceA")
    
    # Worker claims next article from NEW -> should become PROCESSING with lock_flag=1
    claimed = claim_next_article(ArticleState.NEW)
    assert claimed is not None
    assert claimed["id"] == "art_1"
    assert claimed["state"] == ArticleState.NEW  # row returned before update
    
    # Another worker attempting to claim should get None
    second_claim = claim_next_article(ArticleState.NEW)
    assert second_claim is None
    
    # Transition to RANKED
    success = transition_state("art_1", ArticleState.RANKED, score_snapshot={"total_score": 10.0})
    assert success is True

def test_watchdog_releases_zombie_articles(temp_db):
    insert_new_article("zombie_1", "https://site.com/zombie", "Zombie Article", "SourceA")
    claimed = claim_next_article(ArticleState.NEW)
    assert claimed is not None
    
    # Drop trigger temporarily to simulate an article processed 60 minutes ago
    with sm.get_db_connection() as conn:
        conn.execute("DROP TRIGGER IF EXISTS trigger_articles_updated_at")
        conn.execute("UPDATE articles SET updated_at = datetime('now', '-60 minutes') WHERE id = 'zombie_1'")
        conn.commit()
        
    released_count = release_processing_timeout(timeout_minutes=30)
    assert released_count >= 1
    
    # Article should be back in NEW and claimable again
    reclaimed = claim_next_article(ArticleState.NEW)
    assert reclaimed is not None
    assert reclaimed["id"] == "zombie_1"

def test_publish_queue_and_idempotency(temp_db):
    now = int(time.time())
    inserted = insert_to_publish_queue(
        article_id="art_q1",
        headline="BTC HITS 100K",
        content_telegram="Telegram payload",
        content_twitter="Twitter payload",
        content_facebook="Facebook payload",
        article_link="https://ex.com/btc",
        editorial_score=15.0,
        published_ts=now
    )
    assert inserted is True
    
    # Pick best from queue
    picked = pick_best_from_queue("telegram", max_age_hours=6.0)
    assert picked is not None
    assert picked["article_id"] == "art_q1"
    
    # Mark published on telegram
    mark_queue_published("art_q1", "telegram")
    
    # Should not pick this article for telegram anymore
    picked_again = pick_best_from_queue("telegram", max_age_hours=6.0)
    assert picked_again is None

def test_get_best_selected_article_for_jit(temp_db):
    now = int(time.time())
    insert_new_article(
        "art_sel_1",
        "https://ex.com/sel1",
        "Ethereum ETF Staking Approved",
        "CoinDesk",
        summary="SEC approved staking in ETFs",
        published_ts=now
    )
    
    # Mark as SELECTED with score snapshot
    transition_state("art_sel_1", ArticleState.SELECTED, score_snapshot={"editorial_score": 18.0})
    
    candidate = get_best_selected_article("telegram", max_age_hours=6.0)
    assert candidate is not None
    assert candidate["id"] == "art_sel_1"
    assert candidate["editorial_score"] == 18.0

def test_express_seen_and_topic_suppression(temp_db):
    msg = "🔴 Breaking: White House appoints crypto czar!"
    is_dup1 = check_and_insert_express_seen(msg)
    assert is_dup1 is False  # First time: new
    
    is_dup2 = check_and_insert_express_seen(msg)
    assert is_dup2 is True   # Second time: duplicate within 24h
    
    # Shared topic suppression
    fp = "white house||crypto czar"
    assert check_recent_topic(fp, minutes=60) is False
    insert_recent_topic(fp, "EXPRESS")
    assert check_recent_topic(fp, minutes=60) is True
