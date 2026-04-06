import asyncio
import logging
import traceback
import time
from modules.pipeline.collector import collect_articles, get_rss_session
from modules.pipeline.deduplicator import deduplicate_articles
from modules.pipeline.rank import rank_articles
from modules.pipeline.selector import select_top_articles
from modules.pipeline.summarize import summarize_articles, parse_structured_output
from modules.publishing.publisher import publish_all_platforms, publish_single_from_queue, build_content
from modules.express.listener import run_express_listener
from config import TWITTER_CONFIG, EXPRESS_CONFIG, ORCHESTRATION_CONFIG, PLATFORM_MAPPING, reload_config

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


# ==========================================
# TASK 1: CONTENT PIPELINE (chuẩn bị bài → kho)
# ==========================================

async def run_content_pipeline_loop():
    """
    Content Pipeline: quét RSS → dedup → rank → select → summarize → lưu vào publish_queue.
    KHÔNG đăng bài. Việc đăng do run_platform_publisher_loop() đảm nhiệm.
    """
    from modules.state_manager import (
        init_db, insert_new_article, transition_state, ArticleState,
        release_processing_timeout, insert_to_publish_queue
    )
    
    # Startup Delay
    logger.info(f"⏳ [CONTENT PIPELINE] Production Boot Delay: Waiting 30s for network stability...")
    await asyncio.sleep(30)
    
    is_first_cycle = True
    
    init_db()
    release_processing_timeout(timeout_minutes=30)
    
    while True:
        reload_config()
        
        if not ORCHESTRATION_CONFIG.get("rss_enabled", True):
            logger.info("⏸️ [CONTENT PIPELINE] RSS Lane is DISABLED in config. Sleeping...")
            await asyncio.sleep(60)
            continue
        
        logger.info("\n=== [CONTENT PIPELINE] WAKING UP FOR NEW CYCLE ===")
        metrics = {"collected_count": 0, "dedup_kept": 0, "ranked_count": 0, "selected_count": 0, "queued_count": 0}
        
        try:
            # Phase 1: Collect
            articles = await collect_articles()
            metrics["collected_count"] = len(articles) if articles else 0
            if not articles:
                logger.warning("[CONTENT PIPELINE] No articles fetched.")
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
                        
                        # Skip summarize on first cycle (deploy-spam guard)
                        if is_first_cycle:
                            logger.info("🛡️ [CONTENT PIPELINE] STARTUP GUARD: Skipping first cycle to avoid deploy-spam.")
                        else:
                            # Phase 5: Summarize
                            summarized_articles = summarize_articles(selected_articles)
                            
                            if summarized_articles:
                                for art in summarized_articles:
                                    transition_state(art["id"], ArticleState.PROCESSING)
                                    
                                    # Format nội dung cho từng platform và lưu vào kho
                                    content_tg = build_content(art, "telegram", "RSS")
                                    content_tw = build_content(art, "twitter", "RSS")
                                    content_fb = build_content(art, "facebook", "RSS")
                                    
                                    editorial_score = art.get("score", 0)
                                    published_ts = art.get("published_ts", 0)
                                    headline = art.get("structured_content", {}).get("headline", art.get("title", ""))
                                    link = art.get("link", "")
                                    
                                    inserted = insert_to_publish_queue(
                                        art["id"], headline, content_tg, content_tw, content_fb,
                                        link, editorial_score, published_ts
                                    )
                                    if inserted:
                                        metrics["queued_count"] += 1
                                        logger.info(f"📦 [QUEUE] Article '{art['id']}' → kho (score={editorial_score:.1f})")
                                    else:
                                        logger.debug(f"📦 [QUEUE] Article '{art['id']}' already in queue.")
        
        except Exception as e:
            logger.error(f"PIPELINE ERROR: {e}\n{traceback.format_exc()}")
        finally:
            is_first_cycle = False
            logger.info("\n=== [CONTENT PIPELINE] CYCLE END ===")
            logger.info(f"Collected: {metrics['collected_count']} | Dedup: {metrics['dedup_kept']} | Queued: {metrics['queued_count']}")
            try:
                from modules.state_manager import perform_routine_maintenance
                perform_routine_maintenance()
            except: pass
            
            # Sleep theo content_pipeline_interval
            interval_min = ORCHESTRATION_CONFIG.get("content_pipeline_interval_minutes", 30)
            wait_time = max(interval_min * 60, 60)
            logger.info(f"💤 [CONTENT PIPELINE] Sleeping for {interval_min}m...")
            await asyncio.sleep(wait_time)


# ==========================================
# TASK 2: PLATFORM PUBLISHER (check timing → đăng)
# ==========================================

async def run_platform_publisher_loop():
    """
    Per-Platform Publisher: mỗi vài phút check timing từng nền tảng,
    nếu đến giờ → lấy bài tốt nhất từ kho → đăng.
    """
    from modules.state_manager import (
        init_db, pick_best_from_queue, mark_queue_published,
        transition_state, ArticleState, insert_recent_topic
    )
    from modules.publishing.timing import should_publish_now
    from modules.express.fingerprint import extract_fingerprints
    
    # Startup delay — đợi content pipeline chạy trước ít nhất 1 cycle
    startup_delay = 60  # 60s
    logger.info(f"⏳ [PLATFORM PUBLISHER] Waiting {startup_delay}s for content pipeline to warm up...")
    await asyncio.sleep(startup_delay)
    
    init_db()
    
    while True:
        reload_config()
        
        if not ORCHESTRATION_CONFIG.get("rss_enabled", True):
            await asyncio.sleep(60)
            continue
        
        active_platforms = PLATFORM_MAPPING.get("RSS", [])
        max_age = ORCHESTRATION_CONFIG.get("queue_max_age_hours", 12)
        
        for platform in active_platforms:
            try:
                # Bước 1: Check timing rule
                timing_ok = await should_publish_now(platform)
                if not timing_ok:
                    continue
                
                # Bước 2: Lấy bài tốt nhất từ kho
                queue_item = pick_best_from_queue(platform, max_age)
                if not queue_item:
                    logger.info(f"📭 [PLATFORM PUBLISHER] {platform.upper()}: Timing OK nhưng kho trống. Bỏ qua.")
                    continue
                
                adj_score = queue_item.get("adjusted_score", 0)
                headline = queue_item.get("headline", "N/A")
                logger.info(
                    f"📰 [PLATFORM PUBLISHER] {platform.upper()}: "
                    f"Picked '{headline[:60]}' | "
                    f"adjusted_score={adj_score:.1f} | decay={queue_item.get('fresh_decay', 0):.4f}"
                )
                
                # Bước 3: Publish
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, publish_single_from_queue, queue_item, platform, "RSS"
                )
                
                if result.get("success"):
                    # Ghi log publish time cho platform
                    mark_queue_published(queue_item["article_id"], platform)
                    transition_state(queue_item["article_id"], ArticleState.POSTED)
                    
                    # Fingerprint dedup
                    fps = extract_fingerprints(headline)
                    if fps:
                        insert_recent_topic("||".join(fps), 'RSS')
                    
                    logger.info(f"✅ [PLATFORM PUBLISHER] {platform.upper()} → POSTED '{headline[:50]}'")
                elif result.get("is_duplicate"):
                    logger.info(f"⏭️ [PLATFORM PUBLISHER] {platform.upper()} → SKIPPED (already posted)")
                else:
                    logger.error(f"❌ [PLATFORM PUBLISHER] {platform.upper()} → FAILED: {result.get('error')}")
                
            except Exception as e:
                logger.error(f"💥 [PLATFORM PUBLISHER] Error processing {platform}: {e}\n{traceback.format_exc()}")
        
        # Sleep theo publish_check_interval
        check_interval = ORCHESTRATION_CONFIG.get("publish_check_interval_minutes", 5)
        await asyncio.sleep(check_interval * 60)


# ==========================================
# MAIN ENTRY POINT
# ==========================================

async def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s', datefmt='%H:%M:%S')
    
    logger.info("=== STARTING PRODUCTION AI NEWS BOT (V5.0 — Per-Platform Timer) ===")
    
    # 1. Preflight Check
    if not await network_preflight_check():
        logger.error("Preflight check failed. Delaying startup to see if network resolves...")
        await asyncio.sleep(30)
    
    # 2. Start Supervised Tasks
    tasks = [
        # Task 1: Content Pipeline — quét RSS, chuẩn bị bài, lưu kho
        asyncio.create_task(run_supervised_task(run_content_pipeline_loop, "CONTENT_PIPELINE")),
        # Task 2: Platform Publisher — check timing, lấy bài từ kho, đăng
        asyncio.create_task(run_supervised_task(run_platform_publisher_loop, "PLATFORM_PUBLISHER")),
    ]
    
    # Task 3: Express Lane (giữ nguyên)
    if ORCHESTRATION_CONFIG.get("express_enabled", True):
        tasks.append(asyncio.create_task(run_supervised_task(run_express_listener, "EXPRESS_LANE")))
    
    # Task 4: Announcement Scheduler (giữ nguyên)
    try:
        from auto_announcement import run_scheduler_async
        tasks.append(asyncio.create_task(run_supervised_task(run_scheduler_async, "ANNOUNCEMENT_SCHEDULER")))
    except ImportError:
        logger.warning("Could not import auto_announcement. Skipping Announcement Scheduler.")
    
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown signaled.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")

