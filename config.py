import os
from typing import Dict, List, TypedDict

from dotenv import load_dotenv

load_dotenv()

def reload_config():
    """Hot-reload variables from .env without restarting."""
    load_dotenv(override=True)
    
    # Cập nhật lại các biến môi trường nếu cần
    ORCHESTRATION_CONFIG["rss_enabled"] = os.environ.get("RSS_ENABLED", "True").lower() == "true"
    ORCHESTRATION_CONFIG["express_enabled"] = os.environ.get("EXPRESS_ENABLED", "True").lower() == "true"
    ORCHESTRATION_CONFIG["fingerprint_window_minutes"] = int(os.environ.get("FINGERPRINT_WINDOW_MINUTES", "60"))
    ORCHESTRATION_CONFIG["express_throttle_minutes"] = int(os.environ.get("EXPRESS_THROTTLE_MINUTES", "3"))
    ORCHESTRATION_CONFIG["rss_penalty_multiplier"] = float(os.environ.get("RSS_PENALTY_MULTIPLIER", "0.1"))
    ORCHESTRATION_CONFIG["express_retry_attempts"] = int(os.environ.get("EXPRESS_RETRY_ATTEMPTS", "2"))
    ORCHESTRATION_CONFIG["express_retry_backoff_sec"] = int(os.environ.get("EXPRESS_RETRY_BACKOFF_SEC", "30"))
    
    # Reload LLM Provider too
    LLM_CONFIG["active_provider"] = os.environ.get("LLM_PROVIDER", "gemini").lower()

# Mute warnings from Feedparser or any lightweight libs
import warnings
warnings.filterwarnings("ignore")

# --- CÔNG TẮC ĐIỀU KHIỂN NỀN TẢNG (PLATFORM MAPPING) ---
# Quy định luồng nào (RSS, EXPRESS) được đăng lên nền tảng nào.
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS": ["telegram"]  # Có thể thêm "facebook" nếu bật
}

# --- CẤU HÌNH DUAL-LANE ORCHESTRATION ---
ORCHESTRATION_CONFIG = {
    "rss_enabled": os.environ.get("RSS_ENABLED", "True").lower() == "true",
    "express_enabled": os.environ.get("EXPRESS_ENABLED", "True").lower() == "true",
    
    "fingerprint_window_minutes": int(os.environ.get("FINGERPRINT_WINDOW_MINUTES", "60")),
    "express_throttle_minutes": int(os.environ.get("EXPRESS_THROTTLE_MINUTES", "3")),
    "rss_penalty_multiplier": float(os.environ.get("RSS_PENALTY_MULTIPLIER", "0.1")),
    
    "express_retry_attempts": int(os.environ.get("EXPRESS_RETRY_ATTEMPTS", "2")),
    "express_retry_backoff_sec": int(os.environ.get("EXPRESS_RETRY_BACKOFF_SEC", "30"))
}

class RssSource(TypedDict):
    id: str
    name: str
    url: str
    credibility_score: float
    latency_advantage_score: float

RSS_SOURCES: List[RssSource] = [
    {
        "id": "cointelegraph",
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "credibility_score": 1.15,
        "latency_advantage_score": 1.05
    },
    {
        "id": "coindesk",
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "credibility_score": 1.15,
        "latency_advantage_score": 1.1
    },
    {
        "id": "theblock",
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "credibility_score": 1.15,
        "latency_advantage_score": 1.1
    },
    {
        "id": "decrypt",
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "credibility_score": 1.1,
        "latency_advantage_score": 1.05
    },
    {
        "id": "cryptoslate",
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "credibility_score": 1.05,
        "latency_advantage_score": 1.05
    },
    {
        "id": "bitcoinmagazine",
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/.rss/full/",
        "credibility_score": 1.1,
        "latency_advantage_score": 1.0
    },
    {
        "id": "beincrypto",
        "name": "BeInCrypto",
        "url": "https://beincrypto.com/feed/",
        "credibility_score": 1.05,
        "latency_advantage_score": 1.05
    },
    {
        "id": "watcherguru",
        "name": "Watcher Guru",
        "url": "https://watcher.guru/news/feed",
        "credibility_score": 1.05,
        "latency_advantage_score": 1.1
    },
    {
        "id": "newsbtc",
        "name": "NewsBTC",
        "url": "https://www.newsbtc.com/feed/",
        "credibility_score": 1.0,
        "latency_advantage_score": 1.0
    },
    {
        "id": "utoday",
        "name": "U.Today",
        "url": "https://u.today/rss",
        "credibility_score": 1.0,
        "latency_advantage_score": 1.0
    },
    {
        "id": "yahoo_finance_crypto",
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "credibility_score": 1.15,
        "latency_advantage_score": 1.0
    },
    {
        "id": "techcrunch_crypto",
        "name": "TechCrunch Crypto",
        "url": "https://techcrunch.com/category/cryptocurrency/feed/",
        "credibility_score": 1.1,
        "latency_advantage_score": 1.0
    }
]

class KeywordCategoryConfig(TypedDict):
    urgent: List[str]
    macro_politics: List[str]
    major_tech: List[str]
    price_analysis: List[str]

class KeywordCapConfig(TypedDict):
    urgent: float
    macro_politics: float
    major_tech: float
    price_analysis: float

class ScoringWeights(TypedDict):
    base_score: float
    keyword_categories: KeywordCategoryConfig
    keyword_caps: KeywordCapConfig
    editorial_verbs: Dict[str, float]
    cross_source_momentum_score: float
    time_decay_lambda_per_hour: float
    topic_novelty_penalty: float
    baseline_keyword_freqs: Dict[str, float]

SCORING_WEIGHTS: ScoringWeights = {
    # Điểm sàn mặc định cho mọi bài báo
    "base_score": 3.0,
    
    # Hàm mũ y=e^(-lambda*x). Lambda 0.05 nghĩa là sau 14h điểm giảm còn 1/2.
    "time_decay_lambda_per_hour": 0.05, 
    
    # Từ khóa chia làm 4 rổ. Bài tính Max-cap của từng rổ cộng lại.
    "keyword_categories": {
        "urgent": ["hack", "scam", "breach", "sues", "arrest", "bankrupt"],
        "macro_politics": ["regulation", "bill", "legislation", "ban", "approval", "court", "sec", "regulator", "government", "policy", "lawsuit", "fed", "inflation", "cpi", "rate", "etf"],
        "major_tech": ["mainnet", "protocol", "hard fork", "network", "roadmap", "partnership", "upgrade", "integration", "launch"],
        "price_analysis": ["predict", "forecast", "analysis", "price prediction", "target", "analyst", "bullish", "bearish"]
    },
    
    # Điểm Trần (Cap) của từng rổ để tránh lạm phát
    "keyword_caps": {
        "urgent": 10.0,
        "macro_politics": 12.0,
        "major_tech": 10.0,
        "price_analysis": -6.0  # Điểm âm (Soft Penalty)
    },
    
    # Compound Regex for specific tech assets (Sử dụng trong rank.py, cấu hình ở đây cho dễ quản lý)
    "compound_tech_regexes": [
        r"bitcoin.*(upgrade|protocol|fork|network)",
        r"ethereum.*(upgrade|hard fork|mainnet|eip|protocol)"
    ],
    "compound_tech_weight": 5.0, # Điểm cộng thêm nếu khớp compound tech
    
    # Dấu hiệu Action Event (Trọn bộ Vĩ mô & Công nghệ)
    "editorial_verbs": {
        "announce": 4.0,
        "approve": 4.0,
        "pass": 4.0,
        "enforce": 4.0,
        "file": 3.5,
        "propose": 3.5,
        "launch": 3.0,
        "upgrade": 3.0,
        "integrate": 3.0,
        "adopt": 3.0
    },
    
    # Cộng thêm nếu bài nằm trong rổ chủ đề đang rầm rộ
    "cross_source_momentum_score": 2.5,
    
    # Phạt bài viết chung chủ đề với bài xếp trên nó (Diversity Check ở Phase 4)
    # 0.4 nghĩa là phạt mất 60% tổng điểm
    "topic_novelty_penalty": 0.4,
    
    # Tần suất gốc cấy sẵn cho Cold-Start AI (V2)
    "baseline_keyword_freqs": {
        "bitcoin": 50.0,
        "btc": 50.0,
        "ethereum": 40.0,
        "eth": 40.0,
        "etf": 30.0,
        "sec": 20.0,
        "binance": 20.0,
        "coinbase": 15.0,
        "hack": 5.0,
        "scam": 5.0,
        "bankrupt": 5.0
    }
}

# --- CẤU HÌNH CHO PHASE 5: TÓM TẮT & TWEET ---
LLM_CONFIG = {
    # Chọn nhà cung cấp: "openai" hoặc "gemini"
    "active_provider": os.environ.get("LLM_PROVIDER", "gemini").lower(),
    
    "openai": {
        "api_key": os.environ.get("OPENAI_API_KEY", "dummy_key_for_test"),
        "model": "gpt-3.5-turbo",
    },
    
    "gemini": {
        "api_key": os.environ.get("GEMINI_API_KEY", "dummy_key_for_test"),
        "model": "gemini-2.5-flash", # Nâng cấp lên model Gemini 2.5 Flash mới nhất
    },
    
    "max_tokens": 150,
    "temperature": 0.3, # Giữ temperature thấp để tránh AI "ảo giác" (hallucination)
    "timeout_sec": 15,
    "max_retries": 2
}

LLM_PROMPT_CONFIG = {
    # Tương thích ngược: Fallback nếu không định nghĩa template
    "system_prompt": (
        "You are a professional, neutral news editor for a social media bot.\n"
        "Your task is to analyze the provided news article (Title + Summary) and return a structured output.\n"
        "STRICT RULES:\n"
        "1. Write the content entirely in Vietnamese.\n"
        "2. You MUST return the output in exactly this format (using ||| as separator):\n"
        "HEADLINE: <A catchy, short title in Vietnamese>|||SUMMARY: <A detailed summary of the main points in 2-3 sentences>|||HASHTAGS: <1-4 relevant hashtags>\n"
        "3. DO NOT invent facts, numbers, or context. Use exactly what is provided.\n"
        "4. Keep the tone neutral, objective, and strictly informative.\n"
        "5. DO NOT use clickbait, sensationalism, or opinions.\n"
        "6. Do not include URLs."
    )
}

# --- PROMPT TEMPLATES (Hệ thống điều hướng Prompt) ---
# Cho phép override Prompt theo (lane, platform) trong tương lai. Default theo lane.
PROMPT_TEMPLATES = {
    "EXPRESS": (
        "You rewrite breaking news for a Telegram crypto channel.\n"
        "Rules:\n"
        "- Vietnamese only.\n"
        "- Focus on the core event.\n"
        "- Be fast, concise, urgent.\n"
        "- Do NOT invent facts.\n"
        "- If crypto-related, add one short possible market implication.\n"
        "- Use cautious wording: 'có thể', 'thị trường có thể phản ứng'.\n"
        "- If unrelated to crypto markets → IMPACT: 'Chưa rõ tác động'\n"
        "Output format:\n"
        "HEADLINE: <title>|||SUMMARY: <1-2 lines>|||IMPACT: <short implication or 'Chưa rõ tác động'>"
    ),
    "RSS": (
        "You are a neutral macro and technology news reporter for the crypto ecosystem.\n"
        "Analyze the provided article (title + summary).\n"
        "Rules:\n"
        "- Vietnamese only.\n"
        "- Use only given information. Do NOT invent facts.\n"
        "- Tone guideline: factual, neutral, event-focused, no market commentary.\n"
        "- STRICT: Do not speculate about future price direction. Do not give investment advice.\n"
        "- Focus on reporting the event itself rather than interpreting market movements.\n"
        "- Impact must describe possible ecosystem implications (e.g., regulatory clarity, institutional adoption, network development), not price movement.\n"
        "Return exactly:\n"
        "HEADLINE: <short title>|||SUMMARY: <2-3 sentences>|||IMPACT: <ecosystem context or 'Chưa rõ tác động'>|||HASHTAGS: <1-4 tags>"
    )
}

# --- CẤU HÌNH CHO PHASE 3: EVENT ABSTRACTION ---
ADAPTIVE_FATIGUE_WINDOWS = {
    # Tính theo giờ. Default 3 ngày.
    "default": 72,
    "hack": 24,
    "exploit": 24,
    "scam": 24,
    "breach": 24,
    "bankrupt": 24,
    "etf": 168,       # 7 days for long narratives
    "regulation": 168,
    "sec": 168,
    "bill": 168
}

# --- CẤU HÌNH CHO PHASE 6: PUBLISHER (TWITTER) ---
TWITTER_CONFIG = {
    # Thay bằng API Key thật hoặc đọc từ biến môi trường (os.environ.get("TWITTER_API_KEY"))
    "api_key": os.environ.get("TWITTER_API_KEY", "dummy_api_key"),
    "api_secret": os.environ.get("TWITTER_API_SECRET", "dummy_api_secret"),
    "access_token": os.environ.get("TWITTER_ACCESS_TOKEN", "dummy_access_token"),
    "access_secret": os.environ.get("TWITTER_ACCESS_SECRET", "dummy_access_secret"),
    
    # Bật cờ này trong lúc dev/test để tránh gọi API thật lên Twitter
    #"dry_run": os.environ.get("PUBLISH_DRY_RUN", "True").lower() == "true",
    "dry_run": False,
    
    # Yêu cầu về độ dài
    "target_length": 600,
    "hard_max_length": 800,
    
    # Retry Backoff
    "max_retries": 3,
    "backoff_factor": 2.0
}

# --- CẤU HÌNH CHO PHASE 6: PUBLISHER (TELEGRAM) ---
TELEGRAM_CONFIG = {
    "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
}

# --- CẤU HÌNH CHO PHASE 6: PUBLISHER (FACEBOOK) ---
FACEBOOK_CONFIG = {
    "page_access_token": os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
    "page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
}

# --- CẤU HÌNH NƠI LẤY TIN EXPRESS TELEGRAM (PHASE 1) ---
EXPRESS_CONFIG = {
    # Bật chức năng nhận tin Express (Hỗ trợ cấu hình cũ, ưu tiên ORCHESTRATION_CONFIG)
    "express_enabled": os.environ.get("EXPRESS_ENABLED", "True").lower() == "true",
    
    # Telegram API settings cho Telethon/Pyrogram (Lấy từ my.telegram.org)
    "api_id": os.environ.get("TG_API_ID", "dummy_api_id"),
    "api_hash": os.environ.get("TG_API_HASH", "dummy_api_hash"),
    
    # Số điện thoại mặc định (Format: +84...)
    "phone": os.environ.get("TG_PHONE", "dummy_phone"),
    
    # Kênh Telegram nguồn để theo dõi lấy tin (Có thể là ID hoặc username)
    # Ví dụ: '@Coin369' hoặc ID. (Dùng '@me' hoặc 'me' để test nếu nhắn cho Saved Messages)
    "source_channel": os.environ.get("TG_SOURCE_CHANNEL", "me"), 
}

# --- CẤU HÌNH RSS LOOP THỜI GIAN CHỜ ---
RSS_LOOP_INTERVAL = 120 * 60 # 15 minutes by default

# Thư mục chứa Data
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
