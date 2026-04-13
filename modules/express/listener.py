import asyncio
import logging
import time
from telethon import TelegramClient, events
from config import EXPRESS_CONFIG
from modules.state_manager import check_and_insert_express_seen, check_recent_topic, insert_recent_topic
from modules.express.filter import score_express_message
from modules.express.fingerprint import extract_fingerprints
from modules.pipeline.summarize import call_llm_with_retry, parse_structured_output, get_prompt
from config import EXPRESS_CONFIG, ORCHESTRATION_CONFIG, reload_config
from modules.publishing.publisher import publish_all_platforms
import hashlib

logger = logging.getLogger("EXPRESS_LISTENER")

# Cờ báo hiệu (Indicator) từ người dùng Telegram để nhận biết đây là tin nhanh
# Ví dụ: Tin nhắn có chứa icon hình chấm đỏ "🔴" hoặc "🔵"
INDICATORS = ["🔴"] #"🔵", "🆘", "🔥"

class ExpressListener:
    def __init__(self):
        self.enabled = EXPRESS_CONFIG.get("express_enabled", False)
        self.phone = EXPRESS_CONFIG.get("phone")
        self.source_channel = EXPRESS_CONFIG.get("source_channel")
        self.client = None
        
        # Phase 8: Throttle Control
        self.last_publish_time = 0.0

    async def start(self):
        """Khởi động Listener với Reconnection State Machine (Production Grade)."""
        if not self.enabled:
            logger.info("Express Lane is DISABLED in config.")
            return
        
        from modules.publishing.telethon_client import get_shared_telethon_client, is_client_available
        
        if not is_client_available():
            logger.warning("Telegram API ID/Hash is not configured properly. Express Listener cannot start.")
            return

        # Dùng shared Telethon client (singleton)
        self.client = get_shared_telethon_client()
        if not self.client:
            logger.error("Failed to get shared Telethon client.")
            return
        
        # Register Handler
        @self.client.on(events.NewMessage(chats=self.source_channel))
        async def handler(event):
            await self.handle_new_message(event)

        # Connection State Machine Loop
        backoff = 5
        while True:
            try:
                if not self.client.is_connected():
                    logger.info("Connecting to Telegram API...")
                    await self.client.start(phone=self.phone)
                
                # Verify Authorization
                if not await self.client.is_user_authorized():
                    logger.error("🛑 Telegram Session is NOT authorized. Please login locally first and update TG_STRING_SESSION.")
                    return # Exit to let Supervisor handle or wait

                logger.info("✅ Telegram Connected & Authorized. Listening...")
                backoff = 5 # Reset backoff on success
                
                await self.client.run_until_disconnected()
                
            except Exception as e:
                logger.error(f"⚠️ Express Listener connection dropped: {e}")
                logger.info(f"🔄 Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                # Exponential backoff 5s -> 10s ... -> 300s
                backoff = min(backoff * 2, 300)

    async def handle_new_message(self, event):
        """Hàm xử lý khi có tin nhắn mới."""
        # Phase 9: Hot-Reload Config
        reload_config()
        
        message_text = event.raw_text
        if not message_text:
            return

        # Phase 1: Bắt được tin Telegram nhưng chưa đăng
        # Detect tin có icon đỏ
        has_indicator = any(icon in message_text for icon in INDICATORS)
        
        if not has_indicator:
            # Bỏ qua các tin nhắn bình thường (spam, chitchat)
            return
            
        logger.debug(f"🚨 [EXPRESS EVENT] Detected Breaking News from Telegram!")
        
        # Phase 2: Express Hard Dedup (Hash Layer)
        is_duplicate = check_and_insert_express_seen(message_text)
        if is_duplicate:
            logger.debug(f"⚠️ [EXPRESS DEDUP] Blocked duplicate message (already seen in 24h).")
            return
            
        logger.debug(f"✅ [EXPRESS DEDUP] New unique message accepted!")
        logger.debug(f"--- RAW TEXT ---\n{message_text[:100]}...\n----------------")
        
        # Phase 3: Keyword Score Filter
        is_passed, total_score, matched_keywords = score_express_message(message_text)
        
        if not is_passed:
            logger.debug("❌ [EXPRESS FILTER] Message ignored due to low score.")
            return
            
        logger.info("✅ [EXPRESS FILTER] Message passed the score threshold! Proceeding...")
        
        # Phase 4: Proper-Noun Fingerprint Engine
        fingerprints = extract_fingerprints(message_text)
        
        if not fingerprints:
            logger.debug("ℹ️ [EXPRESS FINGERPRINT] No strong entities extracted.")
            # Tạo Fallback Fingerprint từ Top 1-2 Keywords có điểm cao nhất
            sorted_keywords = sorted(matched_keywords.items(), key=lambda x: x[1], reverse=True)
            fallback_keywords = [k for k, v in sorted_keywords[:2] if k != 'has_exclamation']
            
            if fallback_keywords:
                 fingerprint_signature = "||".join(fallback_keywords)
                 logger.debug(f"ℹ️ [EXPRESS FINGERPRINT] Fallback signature generated: {fingerprint_signature}")
            else:
                 short_hash = hashlib.sha256(message_text.encode('utf-8')).hexdigest()[:8]
                 fingerprint_signature = f"fallback||{short_hash}"
                 logger.debug(f"ℹ️ [EXPRESS FINGERPRINT] Deterministic hash fallback used: {fingerprint_signature}")
        else:
            fingerprint_signature = "||".join(fingerprints)
            
        # Phase 5: Express Fingerprint Dedup (Configuration Window)
        # Chỉ Check (Read-Only), việc Insert sẽ diễn ra ở Phase 6 sau khi đăng thành công
        window_minutes = ORCHESTRATION_CONFIG.get("fingerprint_window_minutes", 60)
        is_suppressed = check_recent_topic(fingerprint_signature, minutes=window_minutes)
        
        if is_suppressed:
            logger.warning(f"🛑 [EXPRESS SUPPRESSED] Fingerprint '{fingerprint_signature}' was posted within the last {window_minutes} minutes. Skipping.")
            return
            
        # Phase 8: Minimum Time Gap (Configurable Throttle)
        current_time = time.time()
        time_since_last_publish = current_time - self.last_publish_time
        min_gap_sec = ORCHESTRATION_CONFIG.get("express_throttle_minutes", 3) * 60.0
        if time_since_last_publish < min_gap_sec:
            wait_time = min_gap_sec - time_since_last_publish
            logger.debug(f"⏳ [EXPRESS THROTTLE] Waiting {wait_time:.1f}s before processing to maintain gap...")
            await asyncio.sleep(wait_time)
            
        logger.debug(f"✅ [EXPRESS PUBLISH PIPELINE] Fingerprint '{fingerprint_signature}' is clear! Preparing to publish...")
            
        # Phase 6 & 8: LLM Summarize & Publish (With Delayed Retry)
        article_mock = {
            "id": f"express_{int(time.time())}",
            "title": "Telegram Breaking News",
            "summary": message_text,
            "source_name": self.source_channel,
            "link": ""
        }
        
        system_prompt = get_prompt(lane="EXPRESS")
        user_prompt = f"Source: Telegram Channel {self.source_channel}\n\nTitle: Breaking News\n\nSummary: {message_text}\n\nAnalyze the above and return strictly following the system rules."
        
        max_retries = ORCHESTRATION_CONFIG.get("express_retry_attempts", 2)
        backoff_base = ORCHESTRATION_CONFIG.get("express_retry_backoff_sec", 30)
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                backoff_time = (2 ** (attempt - 1)) * backoff_base
                logger.warning(f"🔄 [EXPRESS RETRY] Attempt {attempt}/{max_retries}. Waiting {backoff_time}s before retry...")
                await asyncio.sleep(backoff_time)
                
            # 6.1: Call LLM
            logger.info(f"🧠 [EXPRESS LLM] Sending to LLM for rewrite (Attempt {attempt})...")
            loop_instance = asyncio.get_running_loop()
            llm_result = await loop_instance.run_in_executor(None, call_llm_with_retry, system_prompt, user_prompt)
            
            if not llm_result:
                logger.error("❌ [EXPRESS LLM] Failed to generate summary in this attempt.")
                if attempt == max_retries:
                    logger.error("🛑 [EXPRESS FATAL] Max retries reached for LLM. Aborting.")
                    return
                continue # Retry
                
            article_mock["tweet_content"] = llm_result
            article_mock["structured_content"] = parse_structured_output(llm_result)
            
            # 6.2: Publish Omni-channel
            logger.info("🚀 [EXPRESS PUBLISH] Firing to Publisher Engine...")
            results = await loop_instance.run_in_executor(None, publish_all_platforms, [article_mock], "EXPRESS")
            
            # 6.3: Post-Publish Check
            res_list = list(results[0]["results"].values())
            is_new_success = any(p.get("success") for p in res_list)
            is_already_posted = all(p.get("is_duplicate") for p in res_list) if res_list else False
            
            if is_new_success or is_already_posted:
                 self.last_publish_time = time.time() # Update Throttle Control
                 if is_new_success:
                     logger.info(f"✅ [EXPRESS LANE] POSTED: Fingerprint '{fingerprint_signature}' successfully sent.")
                     await loop_instance.run_in_executor(None, insert_recent_topic, fingerprint_signature, 'EXPRESS')
                 else:
                     logger.info(f"⏭️ [EXPRESS LANE] SKIPPED: Fingerprint '{fingerprint_signature}' already posted (Idempotency Guard).")
                 return # Phase complete
            else:
                 logger.error(f"❌ [EXPRESS FAILED] Publish engines failed on attempt {attempt}.")
                 if attempt == max_retries:
                     logger.error("🛑 [EXPRESS FATAL] Publish engines failed after all retries. Event dropped.")
                     return
        

    async def stop(self):
        if self.client:
            await self.client.disconnect()
            logger.info("Express Listener STOPPED.")

# Hàm tiện ích để dễ gọi từ main loop
async def run_express_listener():
    listener = ExpressListener()
    await listener.start()
