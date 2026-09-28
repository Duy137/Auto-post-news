import os
import sys
import time
import pytest
import tempfile
import shutil

# Ensure workspace root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from models import Article

@pytest.fixture
def sample_article() -> Article:
    now = int(time.time())
    return {
        "id": "test_sha1_12345",
        "title": "SEC officially approves spot Bitcoin ETF in milestone ruling",
        "link": "https://cointelegraph.com/news/sec-approves-spot-bitcoin-etf",
        "raw_source_url": "https://cointelegraph.com/news/sec-approves-spot-bitcoin-etf?utm_source=rss",
        "summary": "The US Securities and Exchange Commission approved the listing of spot Bitcoin exchange-traded funds.",
        "published_ts": now - 3600,
        "source_name": "CoinTelegraph",
        "score": None,
        "score_detail": None,
        "structured_content": None,
        "tweet_content": None,
        "event_root_id": None
    }

@pytest.fixture
def temp_db(monkeypatch):
    """Provides a fresh isolated SQLite database for state_manager testing."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_article_state.db")
    
    import modules.state_manager as sm
    monkeypatch.setattr(sm, "DATA_DIR", temp_dir)
    monkeypatch.setattr(sm, "DB_PATH", temp_db_path)
    
    sm.init_db()
    
    yield temp_db_path
    
    # Cleanup temp folder after test
    shutil.rmtree(temp_dir, ignore_errors=True)
