import asyncio
import logging
import requests
import feedparser
import time
from typing import List, Optional
from config import RSS_SOURCES, RssSource
from models import Article, normalize_url, generate_article_id

logger = logging.getLogger("COLLECTOR")

# Global session to reuse TCP connections
_rss_session = None

def get_rss_session():
    """Lazily initialize the session with a custom User-Agent."""
    global _rss_session
    if _rss_session is None:
        _rss_session = requests.Session()
        _rss_session.headers.update({
            "User-Agent": "CryptoNewsBot/1.0 (+RSS Aggregator)"
        })
    return _rss_session

async def fetch_feed_with_retry(source: RssSource, max_retries: int = 3) -> Optional[feedparser.FeedParserDict]:
    """
    Fetch RSS feed with production hardening:
    - requests.Session for TCP reuse
    - Split timeouts (3.05s connect, 10s read)
    - Exponential backoff (1s, 2s, 5s) using asyncio.sleep
    - HTTP Status validation (200 only)
    """
    session = get_rss_session()
    backoff_steps = [1, 2, 5]
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Fetching RSS from: {source['name']} (Attempt {attempt+1}/{max_retries})")
            
            # Using loop.run_in_executor for the synchronous requests.get call
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: session.get(source["url"], timeout=(3.05, 10))
            )
            
            if response.status_code != 200:
                logger.warning(f"NETWORK_ERROR: {source['name']} returned HTTP {response.status_code}")
                if attempt < max_retries - 1:
                    wait = backoff_steps[attempt]
                    logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                return None
            
            # Feedparser bridge (parsing is CPU bound, fine to do here or in executor)
            feed = feedparser.parse(response.content)
            
            # Check xml malformed
            if feed.bozo and isinstance(feed.bozo_exception, Exception):
                logger.warning(f"RSS_PARSE_WARNING: {source['name']} might be partially malformed: {feed.bozo_exception}")
                
            return feed
            
        except requests.exceptions.Timeout:
            logger.warning(f"NETWORK_ERROR: Connection timed out for {source['name']}")
        except requests.exceptions.RequestException as e:
            logger.error(f"NETWORK_ERROR: Request failed for {source['name']}: {str(e)}")
        except Exception as e:
            logger.error(f"FATAL_ERROR: Unexpected error fetching {source['name']}: {str(e)}")
            
        if attempt < max_retries - 1:
            wait = backoff_steps[attempt]
            logger.info(f"Backing off {wait}s before retry...")
            await asyncio.sleep(wait)
            
    logger.error(f"Failed to fetch {source['name']} after {max_retries} attempts.")
    return None

def standardize_entry(entry: feedparser.FeedParserDict, source: RssSource) -> Optional[Article]:
    """Convert a raw RSS entry into our standard Article object."""
    try:
        # Extract link or GUID
        raw_link = entry.get('link', entry.get('id', ''))
        if not raw_link:
            logger.warning(f"Missing link/guid in entry from {source['name']}. Skipping.")
            return None
            
        # Canonicalize the URL
        canonical_link = normalize_url(raw_link)
        
        # deterministic ID using canonical link
        article_id = generate_article_id(canonical_link)
        
        # Best-effort timestamp parsing
        published_ts = int(time.time())
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published_ts = int(time.mktime(entry.published_parsed))
            
        # Build standard object
        article: Article = {
            "id": article_id,
            "title": entry.get('title', 'Unknown Title'),
            "link": canonical_link,
            "raw_source_url": raw_link,
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

async def collect_articles() -> List[Article]:
    """Main pipeline function for Phase 1: Collect."""
    all_articles: List[Article] = []
    
    for source in RSS_SOURCES:
        feed = await fetch_feed_with_retry(source)
        
        if not feed or not hasattr(feed, 'entries'):
            logger.warning(f"No valid entries found (or fetch failed) for {source['name']}")
            continue
            
        # Limit processing to newest 20 items
        entries = feed.entries[:20]
        logger.info(f"Processing top {len(entries)}/{len(feed.entries)} entries for {source['name']}")
        
        source_articles = []
        for entry in entries:
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
