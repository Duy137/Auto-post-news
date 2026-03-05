import asyncio
import logging
import traceback
from modules.collector import collect_articles
from modules.deduplicator import deduplicate_articles
from modules.rank import rank_articles
from modules.selector import select_top_articles
from modules.summarize import summarize_articles
from modules.publisher import publish_all_platforms
from modules.express_listener import run_express_listener
from config import TWITTER_CONFIG, EXPRESS_CONFIG, RSS_LOOP_INTERVAL, ORCHESTRATION_CONFIG, reload_config

async def run_rss_pipeline_loop(logger):
    """Vòng lặp chạy Pipeline định kỳ (Interval-driven RSS Lane)"""
    from modules.state_manager import init_db, insert_new_article, transition_state, ArticleState, release_processing_timeout, insert_recent_topic, clean_old_topics
    from modules.express_fingerprint import extract_fingerprints
    
    init_db()
    # Gỡ rối Zombie lúc đầu giờ
    release_processing_timeout(timeout_minutes=30)  
    
    while True:
        # Phase 9: Hot-Reload Config
        reload_config()
        
        if not ORCHESTRATION_CONFIG.get("rss_enabled", True):
            logger.info("⏸️ [RSS LANE] RSS Lane is DISABLED in config. Sleeping...")
            await asyncio.sleep(60)
            continue
            
        logger.info("\n=== [RSS LANE] WAKING UP FOR NEW CYCLE ===")
        metrics = {
            "collected_count": 0,
            "dedup_kept": 0,
            "ranked_count": 0,
            "selected_count": 0,
            "posted_count": 0,
            "failed_count": 0
        }
    
        try:
            # Phase 1: Collect
            try:
                articles = collect_articles()
                metrics["collected_count"] = len(articles) if articles else 0
                if not articles:
                    logger.warning("[RSS LANE] No articles fetched from any RSS sources. Skipping cycle.")
                    continue
                    
                # [SHADOW MODE] Mirror to DB
                for art in articles:
                    insert_new_article(art["id"], art["link"], art["title"], art["source_name"])
            except Exception as e:
                logger.error(f"FATAL ERROR in Phase 1 (Collect): {e}\n{traceback.format_exc()}")
                continue # Skip current cycle
                
            # Phase 2: Deduplicate (Hard + Soft)
            try:
                unique_articles = deduplicate_articles(articles)
                metrics["dedup_kept"] = len(unique_articles) if unique_articles else 0
                if not unique_articles:
                    logger.info("[RSS LANE] No new unique articles found after deduplication. Sleeping.")
                    pass # Chuyển xuống sleep cuối block
                else:
                    # Phase 3: Rank
                    try:
                        ranked_articles = rank_articles(unique_articles)
                        metrics["ranked_count"] = len(ranked_articles) if ranked_articles else 0
                        
                        # [SHADOW MODE] Mirror to DB
                        for art in ranked_articles:
                            transition_state(art["id"], ArticleState.RANKED, score_snapshot=art.get("score_detail"))
                    except Exception as e:
                        logger.error(f"FATAL ERROR in Phase 3 (Rank): {e}\n{traceback.format_exc()}")
                        continue
                        
                    # Phase 4: Diversity Select
                    try:
                        selected_articles = select_top_articles(ranked_articles, top_n=1)
                        metrics["selected_count"] = len(selected_articles) if selected_articles else 0
                        if not selected_articles:
                            logger.info("[RSS LANE] No articles passed the selection phase. Sleeping.")
                            pass
                        else:
                            # [SHADOW MODE] Mirror to DB
                            for art in selected_articles:
                                transition_state(art["id"], ArticleState.SELECTED)
                    except Exception as e:
                        logger.error(f"FATAL ERROR in Phase 4 (Select): {e}\n{traceback.format_exc()}")
            except Exception as e:
                logger.error(f"FATAL ERROR in Phase 2 (Deduplicate): {e}\n{traceback.format_exc()}")
                continue
            
            # Phase 5: Summarize via LLM
            if 'selected_articles' in locals() and selected_articles:
                try:
                    tweet_ready_articles = summarize_articles(selected_articles)
                    if not tweet_ready_articles:
                        logger.warning("[RSS LANE] LLM summarization failed for all candidates. Sleeping.")
                        pass
                    else:
                        # [SHADOW MODE] Mark processing lock
                        for art in tweet_ready_articles:
                            transition_state(art["id"], ArticleState.PROCESSING)
                            
                        # Phase 6: Publish
                        try:
                            results = publish_all_platforms(tweet_ready_articles, "RSS")
                            
                            for r in results:
                                art_id = r["article_id"]
                                platform_results = r.get("results", {})
                                
                                is_success = False
                                logger.info(f"Article ID: {art_id} | Omnichannel Results:")
                                for p_name, p_res in platform_results.items():
                                    if p_res.get("success"):
                                        is_success = True
                                    status_emoji = "✅ OK" if p_res.get("success") else f"❌ FAILED ({p_res.get('error')})"
                                    logger.info(f"  - [{p_name.upper()}]: {status_emoji} | Post ID: {p_res.get('post_id')}")
                
                                if is_success:
                                    metrics["posted_count"] += 1
                                    transition_state(art_id, ArticleState.POSTED)
                                    
                                    # Phase 7: Insert into shared recent_topics to suppress future duplicates
                                    rss_title = next((a["title"] for a in tweet_ready_articles if a["id"] == art_id), "")
                                    if rss_title:
                                        fingerprints = extract_fingerprints(rss_title)
                                        if fingerprints:
                                            fingerprint_signature = "||".join(fingerprints)
                                            # Using run_in_executor to not block the loop, though we are in a non-async function right now technically (it's inside an async func but not awaited)
                                            # Wait, run_rss_pipeline_loop is async. the db call is sync. It's okay to call it directly here since it's just a quick SQLite insert.
                                            insert_recent_topic(fingerprint_signature, 'RSS')
                                else:
                                    metrics["failed_count"] += 1
                                    from modules.state_manager import increment_retry
                                    increment_retry(art_id)
                                    transition_state(art_id, ArticleState.FAILED)
                        except Exception as e:
                            logger.error(f"FATAL ERROR in Phase 6 (Publish): {e}\n{traceback.format_exc()}")
                            
                except Exception as e:
                    logger.error(f"FATAL ERROR in Phase 5 (Summarize): {e}\n{traceback.format_exc()}")
                    
        except Exception as e:
            logger.error(f"UNEXPECTED FATAL ERROR IN PIPELINE: {e}\n{traceback.format_exc()}")
        finally:
            # Ghi log metrics ở the end of the script execution
            logger.info("\n=== [RSS LANE] CLOSING METRICS ===")
            logger.info(f"Collected (Phase 1) : {metrics['collected_count']}")
            logger.info(f"Dedup Kept (Phase 2): {metrics['dedup_kept']}")
            logger.info(f"Ranked (Phase 3)    : {metrics['ranked_count']}")
            logger.info(f"Selected (Phase 4)  : {metrics['selected_count']}")
            logger.info(f"Posted (Phase 6)    : {metrics['posted_count']} successful, {metrics['failed_count']} failed")
            logger.info("==================================\n")
    
            # Cycle done. Clean old memory (Phase 5/7 Memory Control)
            try:
                clean_old_topics(hours=48)
            except Exception as e:
                logger.error(f"Error cleaning old topics: {e}")
                
            logger.info(f"💤 [RSS LANE] Sleeping for {RSS_LOOP_INTERVAL} seconds...")
            await asyncio.sleep(RSS_LOOP_INTERVAL)

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    logger = logging.getLogger("ORCHESTRATOR")
    
    logger.info("=== STARTING DUAL-LANE AI NEWS BOT ===")
    logger.info(f"[CONFIG] DRY_RUN Mode = {TWITTER_CONFIG['dry_run']}")
    logger.info(f"[CONFIG] RSS_ENABLED = {ORCHESTRATION_CONFIG.get('rss_enabled', True)}")
    logger.info(f"[CONFIG] EXPRESS_ENABLED = {ORCHESTRATION_CONFIG.get('express_enabled', True)}")

    tasks = []
    
    # Lane 1: Khởi động RSS Pipeline Loop
    rss_task = asyncio.create_task(run_rss_pipeline_loop(logger))
    tasks.append(rss_task)
    
    # Lane 2: Khởi động Express Telegram Listener
    if ORCHESTRATION_CONFIG.get("express_enabled", True):
        express_task = asyncio.create_task(run_express_listener())
        tasks.append(express_task)
    
    # Đợi mỏi mòn cho các Task bất kì chạy (Luôn luôn chạy do loop while True)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Bot execution cancelled gracefully.")
    except Exception as e:
        logger.error(f"Critical orchestrator error: {e}")

if __name__ == "__main__":
    # Tích hợp vào thư viện asyncio chuẩn
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by User (Ctrl+C). Exiting...")

