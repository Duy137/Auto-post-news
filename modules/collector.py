import time
import logging
from typing import List, Optional
import feedparser

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Article, generate_article_id, normalize_url
from config import RSS_SOURCES, RssSource

# Configure basic logging with different levels capability
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_feed_with_retry(source: RssSource, max_retries: int = 2, delay_sec: int = 3) -> Optional[feedparser.FeedParserDict]:
    """Fetch feed safety with simple retry logic."""
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Fetching RSS from: {source['name']} (Attempt {attempt+1}/{max_retries+1})")
            feed = feedparser.parse(source["url"])
            
            # Check HTTP errs
            if hasattr(feed, 'status') and feed.status not in (200, 301, 302, 304):
                logger.error(f"HTTP Error {feed.status} when fetching {source['name']}")
                return None
                
            # Check xml malformed
            if feed.bozo and isinstance(feed.bozo_exception, Exception):
                logger.warning(f"Feed {source['name']} might be malformed: {feed.bozo_exception}")
                # We still continue because feedparser is good at reading partial/malformed data
                logger.info(f"Continuing to parse {source['name']} despite bozo flag.")
                
            return feed
        except Exception as e:
            logger.error(f"Unexpected error fetching {source['name']} on attempt {attempt+1}: {str(e)}")
            if attempt < max_retries:
                logger.info(f"Retrying in {delay_sec} seconds...")
                time.time.sleep(delay_sec)
            else:
                logger.error(f"Failed to fetch {source['name']} after {max_retries + 1} attempts.")
    return None

def standardize_entry(entry: feedparser.FeedParserDict, source: RssSource) -> Optional[Article]:
    """Convert a raw RSS entry into our standard Article object."""
    try:
        # Extract link
        raw_link = entry.get('link', '')
        if not raw_link:
            logger.warning(f"Missing link in entry from {source['name']}. Skipping.")
            return None
            
        # Canonicalize the URL (remove utm_*, lowercase domain, etc)
        canonical_link = normalize_url(raw_link)
        
        # deterministic ID using canonical link
        article_id = generate_article_id(canonical_link)
        
        # Best-effort timestamp parsing
        published_ts = int(time.time())
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published_ts = int(time.mktime(entry.published_parsed))
            
        # Build standard object from dict
        article: Article = {
            "id": article_id,
            "title": entry.get('title', 'Unknown Title'),
            "link": canonical_link,    # Lưu link sạch
            "raw_source_url": raw_link, # Lưu link thô để audit
            "summary": entry.get('summary', entry.get('description', '')),
            "published_ts": published_ts,
            "source_name": source['name'],
            "score": None,
            "score_detail": None,
            "tweet_content": None
        }
        
        return article
        
    except Exception as e:
        logger.error(f"Fatal error processing entry from {source['name']}: {str(e)}")
        return None

def collect_articles() -> List[Article]:
    """Main pipeline function for Phase 1: Collect."""
    all_articles: List[Article] = []
    
    for source in RSS_SOURCES:
        feed = fetch_feed_with_retry(source)
        
        if not feed or not hasattr(feed, 'entries'):
            logger.warning(f"No valid entries found (or fetch failed) for {source['name']}")
            continue
            
        logger.info(f"Found {len(feed.entries)} entries for {source['name']}")
        
        source_articles = []
        for entry in feed.entries:
            article = standardize_entry(entry, source)
            if article:
                source_articles.append(article)
                
        logger.info(f"Successfully standardized {len(source_articles)} articles from {source['name']}")
        all_articles.extend(source_articles)
        
    logger.info(f"Phase 1 Complete: Total {len(all_articles)} articles collected.")
    return all_articles

if __name__ == "__main__":
    # Test script for Phase 1
    articles = collect_articles()
    if articles:
        print("\n--- SAMPLE ARTICLE ---")
        import json
        print(json.dumps(articles[0], indent=2, ensure_ascii=False))
