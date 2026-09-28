import pytest
from models import normalize_url, generate_article_id

def test_normalize_url_strips_tracking_params():
    url_with_tracking = "https://example.com/crypto/bitcoin-ath/?utm_source=twitter&utm_medium=social&fbclid=12345"
    normalized = normalize_url(url_with_tracking)
    
    assert "utm_source" not in normalized
    assert "utm_medium" not in normalized
    assert "fbclid" not in normalized
    assert normalized == "https://example.com/crypto/bitcoin-ath"

def test_normalize_url_handles_trailing_slash_and_fragments():
    url = "https://Example.Com/News/Market-Update/#comments"
    normalized = normalize_url(url)
    
    assert normalized == "https://example.com/News/Market-Update"

def test_normalize_url_sorts_remaining_params():
    url_a = "https://example.com/api?b=2&a=1"
    url_b = "https://example.com/api?a=1&b=2"
    
    assert normalize_url(url_a) == normalize_url(url_b)

def test_generate_article_id_deterministic():
    url_1 = "https://cointelegraph.com/news/eth-breakout?utm_source=feed"
    url_2 = "https://cointelegraph.com/news/eth-breakout/"
    
    id_1 = generate_article_id(url_1)
    id_2 = generate_article_id(url_2)
    
    assert id_1 == id_2
    assert len(id_1) == 40  # SHA1 hex string length
