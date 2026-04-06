import os
import json
import time
import random
import logging
import requests
import html
from typing import List, Dict, Any, Optional

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import tweepy

from models import Article, PublishResult, PlatformResult
from config import PLATFORM_MAPPING, TWITTER_CONFIG, TELEGRAM_CONFIG, FACEBOOK_CONFIG
import modules.state_manager as sm

logger = logging.getLogger(__name__)

# --- STATE MANAGEMENT ---
# The legacy JSON operations (load/save_posted_history) have been removed.
# Idempotency is now handled via state_manager.py using SQLite (published_events).

# --- FORMATTERS ---
def truncate_tweet_safely(text: str, target_len: int, hard_max_len: int) -> str:
    """Cắt tweet an toàn không cụt chữ."""
    available_text_space = hard_max_len
    if len(text) <= available_text_space:
        return text
    logger.warning(f"Tweet exceeds {hard_max_len} chars. Truncating safely...")
    truncated = text[:available_text_space]
    last_stop = max(truncated.rfind('. '), truncated.rfind('? '), truncated.rfind('! '))
    if last_stop > 0:
        truncated = truncated[:last_stop + 1]
    else:
        last_space = truncated.rfind(' ')
        if last_space > 0:
            truncated = truncated[:last_space] + "..."
        else:
            truncated = truncated[:-3] + "..."
    return truncated

def build_content(article: Article, platform: str, lane: str = "RSS") -> str:
    """Xây dựng format văn bản riêng cho từng kênh và luồng (RSS vs EXPRESS)."""
    struct = article.get("structured_content", {})
    fallback = article.get("tweet_content", "")
    
    headline = struct.get("headline", "")
    summary = struct.get("summary", "")
    impact = struct.get("impact", "")
    hashtags = struct.get("hashtags", "")
    link = article.get("link", "")
    
    # Chuẩn bị block IMPACT nếu có (ẩn đi nếu AI trả về 'Chưa rõ tác động')
    impact_text = ""
    if impact and "chưa rõ tác động" not in impact.lower():
        impact_text = f"\n\n💡 TÁC ĐỘNG: {impact}"
    
    if not headline:
        # Fallback to pure string if LLM prompt parser failed completely
        if platform == "twitter":
            return fallback
        if lane == "EXPRESS":
            return f"🚨 {fallback}"
        return f"📝 {fallback}\n\n🔗 {link}"
        
    # Thoát các ký tự đặc biệt để đảm bảo HTML không lỗi
    safe_headline = html.escape(headline)
    safe_summary = html.escape(summary)
    safe_impact_text = html.escape(impact_text)

    if platform == "twitter":
        # Twitter không render HTML, cần unescape để tránh &amp; &lt; hiển thị thô
        import html as html_module
        clean_headline = html_module.unescape(headline)
        clean_summary = html_module.unescape(summary)
        clean_impact = html_module.unescape(impact_text)
        content = f"{clean_headline}\n\n{clean_summary}{clean_impact}"
        if hashtags:
            content += f"\n\n{hashtags}"
        return truncate_tweet_safely(content, TWITTER_CONFIG["target_length"], TWITTER_CONFIG["hard_max_length"])
    elif platform == "telegram":
        if lane == "EXPRESS":
            return f"🚨 <b>{safe_headline}</b>\n\n{safe_summary}{safe_impact_text}"
        # RSS Default - Dùng nháy kép cho href để Crawler bắt tốt hơn
        return (
            f"📝 <b>{safe_headline}</b>\n\n"
            f"{safe_summary}{safe_impact_text}\n\n"
            f"🔗 <a href=\"{link}\">Đọc bài gốc</a>"
        )
    elif platform == "facebook":
        if lane == "EXPRESS":
            return f"🚨 {headline}\n\n{summary}{impact_text}"
        # RSS Default
        return f"📝 {headline}\n\n{summary}{impact_text}\n\n🔗 {link}"
    return fallback

# --- PUBLISHERS PLUGIN REGISTRY ---
_twitter_client = None

def get_twitter_client(is_dry_run: bool):
    global _twitter_client
    if is_dry_run:
        return None
    if _twitter_client is None:
        _twitter_client = tweepy.Client(
            consumer_key=TWITTER_CONFIG["api_key"],
            consumer_secret=TWITTER_CONFIG["api_secret"],
            access_token=TWITTER_CONFIG["access_token"],
            access_token_secret=TWITTER_CONFIG["access_secret"]
        )
    return _twitter_client

def publish_to_twitter(article: Article, is_dry_run: bool, lane: str = "RSS") -> PlatformResult:
    content = build_content(article, "twitter", lane)
    if is_dry_run:
        logger.info(f"[DRY RUN - TWITTER] Would post:\n{'-'*40}\n{content}\n{'-'*40}")
        return {"success": True, "post_id": f"mock_tw_{int(time.time())}", "error": None}
        
    client = get_twitter_client(False)
    retries = TWITTER_CONFIG["max_retries"]
    backoff = TWITTER_CONFIG["backoff_factor"]
    
    for attempt in range(retries):
        try:
            logger.info(f"Posting to Twitter... (Attempt {attempt+1}/{retries})")
            response = client.create_tweet(text=content)
            return {"success": True, "post_id": response.data['id'], "error": None}
        except tweepy.TooManyRequests as e:
            wait_time = backoff ** attempt * 5
            logger.warning(f"Twitter Rate limited (429). Retrying in {wait_time}s... Error: {e}")
            time.sleep(wait_time)
        except Exception as e:
            logger.error(f"Twitter API Error: {e}")
            return {"success": False, "post_id": None, "error": str(e)}
            
    return {"success": False, "post_id": None, "error": "Max retries exceeded"}

def publish_to_telegram(article: Article, is_dry_run: bool, lane: str = "RSS") -> PlatformResult:
    content = build_content(article, "telegram", lane)
    if is_dry_run:
        logger.info(f"[DRY RUN - TELEGRAM] Would post:\n{'-'*40}\n{content}\n{'-'*40}")
        return {"success": True, "post_id": f"mock_tg_{int(time.time())}", "error": None}
        
    bot_token = TELEGRAM_CONFIG.get("bot_token")
    chat_id = TELEGRAM_CONFIG.get("chat_ids", {}).get(lane)
    if not bot_token or not chat_id:
        return {"success": False, "post_id": None, "error": f"Missing Telegram API config for lane {lane}"}
        
    link = article.get("link", "")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": content, 
        "parse_mode": "HTML",
        "link_preview_options": {
            "url": link,
            "is_disabled": False,
            "prefer_large_media": True,
            "show_above_text": False
        }
    }
    
    try:
        logger.info(f"🚀 TELEGRAM_SEND | chat_id={chat_id} | art_id={article['id']} | msg_len={len(content)}")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {"success": True, "post_id": str(data.get("result", {}).get("message_id")), "error": None}
    except Exception as e:
        logger.error(f"Telegram API Error: {e}")
        return {"success": False, "post_id": None, "error": str(e)}

def publish_to_facebook(article: Article, is_dry_run: bool, lane: str = "RSS") -> PlatformResult:
    content = build_content(article, "facebook", lane)
    if is_dry_run:
        logger.info(f"[DRY RUN - FACEBOOK] Would post:\n{'-'*40}\n{content}\n{'-'*40}")
        return {"success": True, "post_id": f"mock_fb_{int(time.time())}", "error": None}
        
    page_token = FACEBOOK_CONFIG.get("page_access_token")
    page_id = FACEBOOK_CONFIG.get("page_id")
    if not page_token or not page_id:
        return {"success": False, "post_id": None, "error": "Missing Facebook API config"}
        
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    payload = {"message": content, "access_token": page_token}
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {"success": True, "post_id": data.get("id"), "error": None}
    except Exception as e:
        logger.error(f"Facebook API Error: {e}")
        return {"success": False, "post_id": None, "error": str(e)}

PUBLISHERS = {
    "twitter": publish_to_twitter,
    "telegram": publish_to_telegram,
    "facebook": publish_to_facebook
}

# --- SINGLE-PLATFORM PUBLISHER (V5.0 — Per-Platform Timer) ---
def publish_single_from_queue(queue_item: dict, platform: str, lane: str = "RSS") -> PlatformResult:
    """
    Đăng 1 bài từ publish_queue lên 1 nền tảng cụ thể.
    queue_item chứa: content_telegram, content_twitter, content_facebook, article_link, article_id...
    """
    is_dry_run = TWITTER_CONFIG["dry_run"]
    
    content_key = f"content_{platform}"
    content = queue_item.get(content_key, "")
    if not content:
        logger.warning(f"[QUEUE PUBLISH] No content for platform '{platform}' in queue item {queue_item.get('article_id')}")
        return {"success": False, "post_id": None, "error": "Empty content"}
    
    # Tạo article mock để tương thích với publish functions hiện tại
    article_mock = {
        "id": queue_item.get("article_id", ""),
        "title": queue_item.get("headline", ""),
        "link": queue_item.get("article_link", ""),
        "tweet_content": content,
        # Bypass build_content bằng cách đặt structured_content rỗng
        # Content đã được format sẵn khi vào queue
    }
    
    # Idempotency check
    event_fp = queue_item.get("article_id", "")
    if sm.is_event_published(event_fp, platform):
        logger.info(f"⏭️ [QUEUE PUBLISH] Article '{event_fp}' already published on {platform}. Skipping.")
        return {"success": False, "is_duplicate": True, "post_id": "already_posted", "error": "Duplicate"}
    
    publisher_func = PUBLISHERS.get(platform)
    if not publisher_func:
        return {"success": False, "post_id": None, "error": f"No publisher for {platform}"}
    
    try:
        # Publish bằng cách gọi trực tiếp API thay vì qua build_content
        if platform == "telegram":
            res = _publish_raw_telegram(content, queue_item.get("article_link", ""), is_dry_run, lane)
        elif platform == "twitter":
            res = _publish_raw_twitter(content, is_dry_run)
        elif platform == "facebook":
            res = _publish_raw_facebook(content, is_dry_run)
        else:
            res = publisher_func(article_mock, is_dry_run, lane)
        
        if res.get("success"):
            sm.mark_event_published(event_fp, platform, lane)
            logger.info(f"✅ [QUEUE PUBLISH] Article '{event_fp}' → {platform} → SUCCESS (post_id={res.get('post_id')})")
        else:
            logger.error(f"❌ [QUEUE PUBLISH] Article '{event_fp}' → {platform} → FAILED: {res.get('error')}")
        
        return res
    except Exception as e:
        logger.error(f"💥 [QUEUE PUBLISH] Fatal error publishing to {platform}: {e}")
        return {"success": False, "post_id": None, "error": str(e)}


def _publish_raw_telegram(content: str, link: str, is_dry_run: bool, lane: str = "RSS") -> PlatformResult:
    """Đăng nội dung đã format sẵn lên Telegram (không qua build_content)."""
    if is_dry_run:
        logger.info(f"[DRY RUN - TELEGRAM QUEUE] Would post:\n{'-'*40}\n{content}\n{'-'*40}")
        return {"success": True, "post_id": f"mock_tg_{int(time.time())}", "error": None}
    
    bot_token = TELEGRAM_CONFIG.get("bot_token")
    chat_id = TELEGRAM_CONFIG.get("chat_ids", {}).get(lane)
    if not bot_token or not chat_id:
        return {"success": False, "post_id": None, "error": f"Missing Telegram config for lane {lane}"}
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": content,
        "parse_mode": "HTML",
        "link_preview_options": {
            "url": link,
            "is_disabled": False,
            "prefer_large_media": True,
            "show_above_text": False
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {"success": True, "post_id": str(data.get("result", {}).get("message_id")), "error": None}
    except Exception as e:
        return {"success": False, "post_id": None, "error": str(e)}


def _publish_raw_twitter(content: str, is_dry_run: bool) -> PlatformResult:
    """Đăng nội dung đã format sẵn lên Twitter."""
    if is_dry_run:
        logger.info(f"[DRY RUN - TWITTER QUEUE] Would post:\n{'-'*40}\n{content}\n{'-'*40}")
        return {"success": True, "post_id": f"mock_tw_{int(time.time())}", "error": None}
    
    client = get_twitter_client(False)
    try:
        response = client.create_tweet(text=content)
        return {"success": True, "post_id": response.data['id'], "error": None}
    except Exception as e:
        return {"success": False, "post_id": None, "error": str(e)}


def _publish_raw_facebook(content: str, is_dry_run: bool) -> PlatformResult:
    """Đăng nội dung đã format sẵn lên Facebook."""
    if is_dry_run:
        logger.info(f"[DRY RUN - FACEBOOK QUEUE] Would post:\n{'-'*40}\n{content}\n{'-'*40}")
        return {"success": True, "post_id": f"mock_fb_{int(time.time())}", "error": None}
    
    page_token = FACEBOOK_CONFIG.get("page_access_token")
    page_id = FACEBOOK_CONFIG.get("page_id")
    if not page_token or not page_id:
        return {"success": False, "post_id": None, "error": "Missing Facebook config"}
    
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    payload = {"message": content, "access_token": page_token}
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {"success": True, "post_id": data.get("id"), "error": None}
    except Exception as e:
        return {"success": False, "post_id": None, "error": str(e)}


# --- MAIN EXECUTOR (Express Lane + Legacy) ---
def publish_all_platforms(articles: List[Article], source_lane: str = "RSS") -> List[PublishResult]:
    """
    Main Phase 6: Xuất bản lên đa nền tảng.
    Xử lý Plugin Registry, Idempotency, Delay, và Deep Logging.
    """
    results: List[PublishResult] = []
    if not articles:
        return results
        
    is_dry_run = TWITTER_CONFIG["dry_run"] # Use master dry_run toggle for all for now
    
    source_lane = source_lane.upper()
    logger.info(f"Starting Phase 6: Omnichannel Publishing. LANE={source_lane}, DRY_RUN={is_dry_run}")
    
    active_platforms = PLATFORM_MAPPING.get(source_lane, [])
    
    if not active_platforms:
        logger.warning(f"No publishing platforms are mapped for lane: {source_lane}!")
        for art in articles:
            results.append({"article_id": art["id"], "results": {}, "posted_timestamp": None})
        return results

    for idx, article in enumerate(articles):
        art_id = article["id"]
        # Use fingerprint representing the actual entity/event payload instead of just DB id
        event_fp = article.get("fingerprint", "") or art_id
        
        platform_results: dict[str, PlatformResult] = {}
        at_least_one_new_success = False

        for platform_name in active_platforms:
            # Debug log for idempotency key
            logger.debug(f"[IDEMPOTENCY] Checking event_fp: '{event_fp}' for platform: {platform_name}")
            
            if sm.is_event_published(event_fp, platform_name):
                logger.info(f"Idempotency Guard: Event '{event_fp}' already posted on {platform_name}. Skipping.")
                platform_results[platform_name] = {
                    "success": False, 
                    "is_duplicate": True, 
                    "post_id": "already_posted", 
                    "error": "Duplicate"
                }
                continue
                
            publisher_func = PUBLISHERS.get(platform_name)
            if not publisher_func:
                logger.error(f"Publisher function not found for platform: {platform_name}")
                platform_results[platform_name] = {"success": False, "post_id": None, "error": "Plugin missing"}
                continue
                
            try:
                res = publisher_func(article, is_dry_run, source_lane)
                platform_results[platform_name] = res
                if res["success"]:
                    sm.mark_event_published(event_fp, platform_name, source_lane)
                    at_least_one_new_success = True
            except Exception as e:
                logger.error(f"Fatal plugin error for {platform_name}: {e}")
                platform_results[platform_name] = {"success": False, "post_id": None, "error": str(e)}

        results.append({
            "article_id": art_id,
            "results": platform_results,
            "posted_timestamp": int(time.time()) if at_least_one_new_success else None
        })
        
        if at_least_one_new_success and not is_dry_run and idx < len(articles) - 1:
            delay = random.uniform(3, 8)
            logger.info(f"Article processed. Sleeping for {delay:.2f}s to avoid rate limits...")
            time.sleep(delay)

    ok_count = sum(1 for r in results if any(p.get("success") for p in r["results"].values()))
    logger.info(f"Phase 6 Complete: {ok_count}/{len(articles)} articles published to at least 1 platform.")
    return results

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    print("\n[MÔ PHỎNG PHASE 6: PUBLISHER ENGINE (OMNICHANNEL)]\n")
    
    mock_articles: List[Article] = [
        {
            "id": "item_111", 
            "title": "Short Tweet Test", 
            "link": "https://example.com/item1", 
            "raw_source_url": "", "summary": "", "published_ts": 123, "source_name": "SourceA",
            "score": 10.0, "score_detail": None,
            "structured_content": {
                "headline": "This is a headline",
                "summary": "This is a detailed summary of the facts.",
                "hashtags": "#test #news"
            },
            "tweet_content": ""
        }
    ]
    
    PUBLISHING_PLATFORMS["twitter"] = True
    PUBLISHING_PLATFORMS["telegram"] = True
    TWITTER_CONFIG["dry_run"] = True
    
    results = publish_all_platforms(mock_articles)
    
    print("\n--- [DEBUG] PUBLISH RESULTS ---")
    for r in results:
        print(f"Article ID: {r['article_id']}")
        for p_name, p_res in r["results"].items():
            status = "✅ OK" if p_res["success"] else f"❌ FAILED ({p_res['error']})"
            print(f"  - {p_name}: {status} | ID: {p_res['post_id']}")
