"""
Telethon Client Singleton (V5.0)
Chia sẻ 1 Telethon client giữa Express Listener và Platform Publisher (gap check).
"""
import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import EXPRESS_CONFIG

# DATA_DIR — nơi lưu session file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

logger = logging.getLogger(__name__)

_client: TelegramClient = None
_initialized = False

def get_shared_telethon_client() -> TelegramClient:
    """
    Trả về singleton Telethon client.
    Client được tạo 1 lần, dùng chung cho Express Listener và Gap Check.
    Lưu ý: caller phải tự gọi client.start() và client.connect() nếu cần.
    """
    global _client, _initialized
    
    if _initialized and _client is not None:
        return _client
    
    api_id = EXPRESS_CONFIG.get("api_id")
    api_hash = EXPRESS_CONFIG.get("api_hash")
    
    if not api_id or api_id == "dummy_api_id" or not api_hash or api_hash == "dummy_api_hash":
        logger.warning("[TELETHON] API ID/Hash not configured. Shared client unavailable.")
        return None
    
    api_id_int = int(api_id)
    session_val = os.environ.get("TG_STRING_SESSION")
    
    if session_val:
        _client = TelegramClient(StringSession(session_val), api_id_int, api_hash)
    else:
        session_path = os.path.join(DATA_DIR, 'express_session')
        _client = TelegramClient(session_path, api_id_int, api_hash)
    
    _initialized = True
    logger.info("[TELETHON] Shared client created (singleton).")
    return _client

def is_client_available() -> bool:
    """Kiểm tra nhanh xem Telethon client có thể tạo được không."""
    api_id = EXPRESS_CONFIG.get("api_id")
    api_hash = EXPRESS_CONFIG.get("api_hash")
    return bool(api_id and api_id != "dummy_api_id" and api_hash and api_hash != "dummy_api_hash")
