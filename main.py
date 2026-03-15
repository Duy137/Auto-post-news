import asyncio
import logging
import traceback
import time
from modules.collector import collect_articles, get_rss_session
from modules.deduplicator import deduplicate_articles
from modules.rank import rank_articles
from modules.selector import select_top_articles
from modules.summarize import summarize_articles, parse_structured_output
from modules.publisher import publish_all_platforms
from modules.express_listener import run_express_listener
from config import TWITTER_CONFIG, EXPRESS_CONFIG, RSS_LOOP_INTERVAL, ORCHESTRATION_CONFIG, reload_config

logger = logging.getLogger("ORCHESTRATOR")

async def network_preflight_check(max_retries=3, delay=5):
    """Verify outbound internet access before starting lanes."""
    session = get_rss_session()
    test_url = "https://cointelegraph.com/rss"
    
    for i in range(max_retries):
        try:
            logger.info(f"Network Preflight Check: Attempt {i+1}/{max_retries}...")
            # Use a quick connect timeout
            response = await asyncio.get_running_loop().run_in_executor(
                None, 
                lambda: session.get(test_url, timeout=(3.05, 5))
            )
            if response.status_code == 200:
                logger.info("✅ Network Preflight Check: SUCCESS (Internet is reachable)")
                return True
        except Exception as e:
            logger.warning(f"Network Preflight Check: FAILED. Error: {e}")
        
        if i < max_retries - 1:
            await asyncio.sleep(delay)
            
    logger.error("🛑 NETWORK_UNREACHABLE: Outbound internet access check failed after all retries.")
    return False

async def run_supervised_task(task_coro, task_name):
    """Supervisor wrapper that restarts a specific task if it fails."""
    backoff = 5
    while True:
        try:
            logger.info(f"🛡️ [SUPERVISOR] Starting task: {task_name}")
            await task_coro()
            logger.warning(f"⚠️ [SUPERVISOR] Task {task_name} exited normally. Restarting in {backoff}s...")
        except Exception as e:
            logger.error(f"💥 [SUPERVISOR] Task {task_name} CRASHED: {e}\n{traceback.format_exc()}")
            logger.info(f"🔄 [SUPERVISOR] Attempting restart of {task_name} in {backoff}s...")
        
        await asyncio.sleep(backoff)
        # Exponential backoff for restarts (5s to 5m)
        backoff = min(backoff * 2, 300)

async def run_rss_pipeline_loop():
    """Vòng lặp chạy Pipeline định kỳ (Interval-driven RSS Lane) với Boot Delay."""
    from modules.state_manager import init_db, insert_new_article, transition_state, ArticleState, release_processing_timeout, insert_recent_topic
    from modules.express_fingerprint import extract_fingerprints
    
    # 3. Startup Delay for RSS Lane
    logger.info(f"⏳ [RSS LANE] Production Boot Delay: Waiting 15s for network stability...")
    await asyncio.sleep(15)
    
    init_db()
    release_processing_timeout(timeout_minutes=30)  
    
    while True:
        reload_config()
        
        if not ORCHESTRATION_CONFIG.get("rss_enabled", True):
            logger.info("⏸️ [RSS LANE] RSS Lane is DISABLED in config. Sleeping...")
            await asyncio.sleep(60)
            continue
            
        logger.info("\n=== [RSS LANE] WAKING UP FOR NEW CYCLE ===")
        metrics = {"collected_count": 0, "dedup_kept": 0, "ranked_count": 0, "selected_count": 0, "posted_count": 0, "failed_count": 0}
    
        try:
            # Phase 1: Collect (Async now!)
            articles = await collect_articles()
            metrics["collected_count"] = len(articles) if articles else 0
            if not articles:
                logger.warning("[RSS LANE] No articles fetched. Polling interval respected.")
            else:
                for art in articles:
                    insert_new_article(art["id"], art["link"], art["title"], art["source_name"])
                
                # Phase 2: Deduplicate
                unique_articles = deduplicate_articles(articles)
                metrics["dedup_kept"] = len(unique_articles) if unique_articles else 0
                
                if unique_articles:
                    # Phase 3: Rank
                    ranked_articles = rank_articles(unique_articles)
                    metrics["ranked_count"] = len(ranked_articles)
                    for art in ranked_articles:
                        transition_state(art["id"], ArticleState.RANKED, score_snapshot=art.get("score_detail"))
                        
                    # Phase 4: Select
                    selected_articles = select_top_articles(ranked_articles, top_n=1)
                    metrics["selected_count"] = len(selected_articles)
                    
                    if selected_articles:
                        for art in selected_articles:
                            transition_state(art["id"], ArticleState.SELECTED)
                        
                        # Phase 5: Summarize
                        tweet_ready_articles = summarize_articles(selected_articles)
                        if tweet_ready_articles:
                            for art in tweet_ready_articles:
                                transition_state(art["id"], ArticleState.PROCESSING)
                                
                            # Phase 6: Publish
                            results = await asyncio.get_running_loop().run_in_executor(None, publish_all_platforms, tweet_ready_articles, "RSS")
                            
                            for r in results:
                                art_id = r["article_id"]
                                platform_list = list(r.get("results", {}).values())
                                
                                # 1. Was it actually posted in this cycle?
                                new_success = any(p.get("success") for p in platform_list)
                                
                                # 2. Was it skipped because it's ALREADY posted everywhere?
                                all_skipped = all(p.get("is_duplicate") for p in platform_list) if platform_list else False
                                
                                if new_success:
                                    logger.info(f"✅ [RSS LANE] POSTED: Article {art_id} successfully sent to platforms.")
                                    metrics["posted_count"] += 1
                                    transition_state(art_id, ArticleState.POSTED)
                                    # Fingerprint dedup
                                    rss_title = next((a["title"] for a in tweet_ready_articles if a["id"] == art_id), "")
                                    fps = extract_fingerprints(rss_title)
                                    if fps: insert_recent_topic("||".join(fps), 'RSS')
                                elif all_skipped:
                                    logger.info(f"⏭️ [RSS LANE] SKIPPED: Article {art_id} already exists on platforms (Idempotency Guard).")
                                    transition_state(art_id, ArticleState.POSTED) # Ensure state is terminal
                                else:
                                    # Partial failure or total failure
                                    metrics["failed_count"] += 1
                                    transition_state(art_id, ArticleState.FAILED)

        except Exception as e:
            logger.error(f"PIPELINE ERROR: {e}\n{traceback.format_exc()}")
        finally:
            logger.info("\n=== [RSS LANE] CYCLE END ===")
            logger.info(f"Collected: {metrics['collected_count']} | Posted: {metrics['posted_count']}")
            try:
                from modules.state_manager import perform_routine_maintenance
                perform_routine_maintenance()
            except: pass
            
            # Polling Control: Ensure at least 60s
            wait_time = max(RSS_LOOP_INTERVAL, 60)
            logger.info(f"💤 [RSS LANE] Sleeping for {wait_time} seconds...")
            await asyncio.sleep(wait_time)

async def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s', datefmt='%H:%M:%S')
    
    logger.info("=== STARTING PRODUCTION AI NEWS BOT ===")
    
    # 1. Preflight Check
    if not await network_preflight_check():
        logger.error("Preflight check failed. Delaying startup to see if network resolves...")
        await asyncio.sleep(30) # Wait a bit before starting anyway, just in case
    
    # 2. Start Supervised Tasks
    tasks = [
        asyncio.create_task(run_supervised_task(run_rss_pipeline_loop, "RSS_LANE"))
    ]
    
    if ORCHESTRATION_CONFIG.get("express_enabled", True):
        tasks.append(asyncio.create_task(run_supervised_task(run_express_listener, "EXPRESS_LANE")))
    
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown signaled.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
