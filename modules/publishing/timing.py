"""
Publish Timing Module (V5.0)
Quyết định thời điểm đăng bài cho từng platform: gap / scheduled / interval.
"""
import math
import logging
import datetime
from typing import Optional

from config import ORCHESTRATION_CONFIG, SCORING_WEIGHTS

logger = logging.getLogger(__name__)

# Múi giờ Việt Nam
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))


async def should_publish_now(platform: str) -> bool:
    """
    Kiểm tra xem platform có nên đăng bài ngay lúc này không.
    Đọc timing config từ ORCHESTRATION_CONFIG["platform_timing"][platform].
    
    Returns:
        True nếu đến giờ đăng, False nếu chưa.
    """
    timing = ORCHESTRATION_CONFIG.get("platform_timing", {}).get(platform)
    if not timing:
        logger.warning(f"[TIMING] No timing config for platform '{platform}'. Skipping.")
        return False
    
    mode = timing.get("mode", "interval")
    
    if mode == "gap":
        return await _check_gap_mode(platform, timing)
    elif mode == "scheduled":
        return _check_scheduled_mode(platform, timing)
    elif mode == "interval":
        return _check_interval_mode(platform, timing)
    else:
        logger.warning(f"[TIMING] Unknown mode '{mode}' for {platform}. Skipping.")
        return False


async def _check_gap_mode(platform: str, timing: dict) -> bool:
    """
    Gap mode: check khoảng cách từ bài cuối trên channel.
    - Telegram: dùng Telethon API nếu có, fallback về DB nội bộ
    - Các platform khác: dùng DB nội bộ
    """
    min_gap_hours = timing.get("min_gap_hours", 4)
    
    last_msg_time = None
    
    # Telegram: ưu tiên check channel qua Telethon (async native)
    if platform == "telegram":
        channel_id = timing.get("gap_channel_id", "")
        if channel_id:
            last_msg_time = await get_telegram_channel_last_msg_time(channel_id)
    
    # Fallback: check DB nội bộ
    if last_msg_time is None:
        last_msg_time = _get_last_publish_from_db(platform)
    
    if last_msg_time is None:
        logger.info(f"📡 [TIMING:{platform.upper()}] Gap mode: chưa từng đăng → cho phép đăng.")
        return True
    
    now = datetime.datetime.now(VN_TZ)
    gap_hours = (now - last_msg_time).total_seconds() / 3600.0
    
    if gap_hours >= min_gap_hours:
        logger.info(f"📡 [TIMING:{platform.upper()}] Gap mode: {gap_hours:.1f}h >= {min_gap_hours}h → ĐẾN GIỜ ĐĂNG.")
        return True
    else:
        logger.debug(f"📡 [TIMING:{platform.upper()}] Gap mode: {gap_hours:.1f}h < {min_gap_hours}h → chưa đến giờ.")
        return False


def _check_scheduled_mode(platform: str, timing: dict) -> bool:
    """Scheduled mode: check nếu bây giờ nằm trong ±5 phút của 1 slot."""
    schedule = timing.get("schedule", [])
    if not schedule:
        logger.warning(f"[TIMING:{platform.upper()}] Scheduled mode nhưng schedule rỗng. Skipping.")
        return False
    
    now = datetime.datetime.now(VN_TZ)
    tolerance_minutes = 5  # ±5 phút
    
    for t_str in schedule:
        try:
            h, m = map(int, t_str.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            diff_minutes = abs((now - target).total_seconds()) / 60.0
            
            if diff_minutes <= tolerance_minutes:
                # Check xem đã đăng trong window này chưa (tránh đăng 2 lần trong cùng slot)
                last_pub = _get_last_publish_from_db(platform)
                if last_pub:
                    since_last = (now - last_pub).total_seconds() / 60.0
                    if since_last < tolerance_minutes * 2:
                        logger.debug(f"📡 [TIMING:{platform.upper()}] Scheduled {t_str}: đã đăng {since_last:.0f}m trước trong slot này.")
                        return False
                
                logger.info(f"📡 [TIMING:{platform.upper()}] Scheduled mode: khớp slot {t_str} → ĐẾN GIỜ ĐĂNG.")
                return True
        except (ValueError, AttributeError):
            logger.warning(f"[TIMING] Invalid schedule format: '{t_str}'. Expected HH:MM.")
            continue
    
    return False


def _check_interval_mode(platform: str, timing: dict) -> bool:
    """Interval mode: cách đều N giờ kể từ lần đăng trước (check DB nội bộ)."""
    interval_hours = timing.get("interval_hours", 4)
    
    last_pub = _get_last_publish_from_db(platform)
    if last_pub is None:
        logger.info(f"📡 [TIMING:{platform.upper()}] Interval mode: chưa từng đăng → cho phép đăng.")
        return True
    
    now = datetime.datetime.now(VN_TZ)
    hours_since = (now - last_pub).total_seconds() / 3600.0
    
    if hours_since >= interval_hours:
        logger.info(f"📡 [TIMING:{platform.upper()}] Interval mode: {hours_since:.1f}h >= {interval_hours}h → ĐẾN GIỜ ĐĂNG.")
        return True
    else:
        logger.debug(f"📡 [TIMING:{platform.upper()}] Interval mode: {hours_since:.1f}h < {interval_hours}h → chưa đến giờ.")
        return False


def _get_last_publish_from_db(platform: str) -> Optional[datetime.datetime]:
    """Lấy thời điểm đăng cuối từ DB, parse thành datetime aware (VN_TZ)."""
    from modules.state_manager import get_last_publish_time_db
    
    ts_str = get_last_publish_time_db(platform)
    if not ts_str:
        return None
    
    try:
        # SQLite CURRENT_TIMESTAMP trả về UTC
        dt_utc = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
        return dt_utc.astimezone(VN_TZ)
    except (ValueError, TypeError):
        return None


async def get_telegram_channel_last_msg_time(channel_id: str) -> Optional[datetime.datetime]:
    """
    Async — gọi từ async context (platform publisher loop).
    Lấy thời gian tin nhắn cuối trên Telegram channel qua Telethon API.
    """
    from modules.publishing.telethon_client import get_shared_telethon_client
    
    client = get_shared_telethon_client()
    if not client:
        return None
    
    try:
        if not client.is_connected():
            logger.debug("[TIMING] Telethon client not connected, skipping gap check.")
            return None
        
        # Lấy 1 tin nhắn gần nhất trên channel
        # channel_id có thể là username ("@channel") hoặc numeric ID
        try:
            entity = int(channel_id)
        except ValueError:
            entity = channel_id
        
        messages = await client.get_messages(entity, limit=1)
        if messages and len(messages) > 0:
            msg_time = messages[0].date  # datetime UTC aware
            msg_time_vn = msg_time.astimezone(VN_TZ)
            logger.info(f"📡 [TIMING:TELEGRAM] Last message on channel: {msg_time_vn.strftime('%H:%M:%S %d/%m')}")
            return msg_time_vn
        
        return None
    except Exception as e:
        logger.warning(f"[TIMING] Telethon get_messages failed: {e}")
        return None


def calc_adjusted_score(editorial_score: float, published_ts: int) -> float:
    """Tính lại score với time_decay tại thời điểm hiện tại."""
    import time
    current_ts = int(time.time())
    lmbda = SCORING_WEIGHTS.get("time_decay_lambda_per_hour", 0.035)
    
    MIN_VALID_TS = 1577836800  # 2020-01-01
    if not published_ts or published_ts < MIN_VALID_TS:
        published_ts = current_ts
    
    hours_passed = max((current_ts - published_ts) / 3600.0, 0)
    fresh_decay = max(math.exp(-lmbda * hours_passed), 0.12)
    return round(editorial_score * fresh_decay, 2)
