import pytest
from modules.pipeline.deduplicator import (
    normalize_text_phrases,
    normalize_tokens,
    get_words,
    get_slug_from_url,
    calculate_jaccard_similarity,
    EnhancedSimilarity,
    deduplicate_articles
)

def test_normalize_text_phrases():
    raw_text = "The U.S. Securities and Exchange Commission sued the entity"
    normalized = normalize_text_phrases(raw_text)
    assert "sec" in normalized
    assert "securities and exchange commission" not in normalized

def test_normalize_tokens():
    tokens = {"btc", "eth", "sol", "binance"}
    normalized = normalize_tokens(tokens)
    assert "bitcoin" in normalized
    assert "ethereum" in normalized
    assert "solana" in normalized

def test_get_words_and_slug():
    url = "https://cointelegraph.com/news/bitcoin-surges-past-90k-today"
    slug = get_slug_from_url(url)
    words = get_words(slug)
    
    assert "bitcoin" in words
    assert "surges" in words
    assert "90k" in words

def test_calculate_jaccard_similarity():
    set_a = {"sec", "lawsuit", "coinbase", "dismissed"}
    set_b = {"sec", "lawsuit", "coinbase", "court"}
    
    sim = calculate_jaccard_similarity(set_a, set_b)
    # Intersection = 3 {"sec", "lawsuit", "coinbase"}, Union = 5
    assert sim == pytest.approx(3 / 5, 0.01)

def test_enhanced_similarity_high_on_same_event():
    engine = EnhancedSimilarity()
    
    art_a = {
        "title": "SEC drops lawsuit against Coinbase",
        "link": "https://coindesk.com/sec-drops-lawsuit-coinbase"
    }
    art_b = {
        "title": "U.S. Regulator Drops Charges Against Coinbase",
        "link": "https://cryptoslate.com/us-regulator-drops-charges-coinbase"
    }
    
    sim = engine.calculate_similarity(art_a, art_b)
    assert sim >= 0.38  # Default SIMILARITY_THRESHOLD is 0.38

def test_enhanced_similarity_low_on_different_events():
    engine = EnhancedSimilarity()
    
    art_a = {
        "title": "SEC drops lawsuit against Coinbase",
        "link": "https://coindesk.com/sec-drops-lawsuit-coinbase"
    }
    art_b = {
        "title": "Solana ecosystem hits new daily active address milestone",
        "link": "https://decrypt.co/solana-active-addresses-record"
    }
    
    sim = engine.calculate_similarity(art_a, art_b)
    assert sim < 0.20

def test_deduplicate_articles_clusters_in_batch(temp_db):
    now = 1700000000
    articles = [
        {
            "id": "art_1",
            "title": "SEC drops lawsuit against Coinbase in court ruling",
            "link": "https://source1.com/sec-drops-coinbase-case",
            "published_ts": now,
            "source_name": "SourceA",
            "summary": "SEC officially ended the lawsuit against Coinbase."
        },
        {
            "id": "art_2",
            "title": "U.S. Regulator Drops Charges Against Coinbase",
            "link": "https://source2.com/us-regulator-drops-charges-coinbase",
            "published_ts": now + 60,
            "source_name": "SourceB",
            "summary": "Charges against Coinbase have been dropped."
        },
        {
            "id": "art_3",
            "title": "Ethereum developers schedule Pectra upgrade for testnet",
            "link": "https://source3.com/ethereum-pectra-upgrade-testnet",
            "published_ts": now + 120,
            "source_name": "SourceC",
            "summary": "Developers announced testnet date."
        }
    ]
    
    unique = deduplicate_articles(articles)
    
    # 2 articles about SEC/Coinbase should cluster into 1 Lead Article
    # 1 article about Ethereum upgrade is separate
    assert len(unique) == 2
    lead_article = next(a for a in unique if "Coinbase" in a["title"])
    assert lead_article.get("cluster_size") == 2
    assert lead_article.get("event_root_id") is not None
