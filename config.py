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
    ORCHESTRATION_CONFIG["express_retry_backoff_sec"] = int(os.environ.get("express_retry_backoff_sec", "30"))
    ORCHESTRATION_CONFIG["rss_mode"] = os.environ.get("RSS_MODE", "interval").lower()
    ORCHESTRATION_CONFIG["rss_schedule"] = [t.strip() for t in os.environ.get("RSS_SCHEDULE", "08:00,11:00,14:00,17:00,20:00,23:00").split(",") if t.strip()]
    
    # Reload LLM Provider too
    LLM_CONFIG["active_provider"] = os.environ.get("LLM_PROVIDER", "gemini").lower()
    
    # Reload API Keys into lists
    LLM_CONFIG["openai"]["api_keys"] = [k for k in [os.environ.get(f"OPENAI_API_KEY_{i}") for i in range(1, 10)] + [os.environ.get("OPENAI_API_KEY")] if k]
    if not LLM_CONFIG["openai"]["api_keys"]:
        LLM_CONFIG["openai"]["api_keys"] = ["dummy_key_for_test"]
        
    LLM_CONFIG["gemini"]["api_keys"] = [k for k in [os.environ.get(f"GEMINI_API_KEY_{i}") for i in range(1, 10)] + [os.environ.get("GEMINI_API_KEY")] if k]
    if not LLM_CONFIG["gemini"]["api_keys"]:
        LLM_CONFIG["gemini"]["api_keys"] = ["dummy_key_for_test"]

# Mute warnings from Feedparser or any lightweight libs
import warnings
warnings.filterwarnings("ignore")

# --- CÔNG TẮC ĐIỀU KHIỂN NỀN TẢNG (PLATFORM MAPPING) ---
# Quy định luồng nào (RSS, EXPRESS) được đăng lên nền tảng nào.
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS": ["telegram"]  # Thêm twitter để test Dry Run
}

# --- CẤU HÌNH DUAL-LANE ORCHESTRATION ---
ORCHESTRATION_CONFIG = {
    "rss_enabled": os.environ.get("RSS_ENABLED", "True").lower() == "true",
    "express_enabled": os.environ.get("EXPRESS_ENABLED", "True").lower() == "true",
    
    "fingerprint_window_minutes": int(os.environ.get("FINGERPRINT_WINDOW_MINUTES", "60")),
    "express_throttle_minutes": int(os.environ.get("EXPRESS_THROTTLE_MINUTES", "3")),
    "rss_penalty_multiplier": float(os.environ.get("RSS_PENALTY_MULTIPLIER", "0.1")),
    
    "express_retry_attempts": int(os.environ.get("EXPRESS_RETRY_ATTEMPTS", "2")),
    "express_retry_backoff_sec": int(os.environ.get("EXPRESS_RETRY_BACKOFF_SEC", "30")),
    
    # RSS Mechanism: 'interval' (cách 1 khoảng) hoặc 'scheduled' (theo giờ cố định)
    "rss_mode": os.environ.get("RSS_MODE", "interval").lower(),
    "rss_schedule": [t.strip() for t in os.environ.get("RSS_SCHEDULE", "07:00,11:00,15:00,18:00,21:00,00:00").split(",") if t.strip()]
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
        "credibility_score": 1.25,
        "latency_advantage_score": 1.1
    },
    {
        "id": "coindesk",
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "credibility_score": 1.2,
        "latency_advantage_score": 1.15
    },
    {
        "id": "theblock",
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "credibility_score": 1.2,
        "latency_advantage_score": 1.15
    },
    {
        "id": "decrypt",
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "credibility_score": 1.15,
        "latency_advantage_score": 1.1
    },
    {
        "id": "investing_crypto",
        "name": "Investing.com Crypto",
        "url": "https://www.investing.com/rss/news_301.rss",
        "credibility_score": 1.15,
        "latency_advantage_score": 1.05
    },
    {
        "id": "cryptoslate",
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "credibility_score": 1.00,
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
        "id": "techcrunch_crypto",
        "name": "TechCrunch Crypto",
        "url": "https://techcrunch.com/category/cryptocurrency/feed/",
        "credibility_score": 1.1,
        "latency_advantage_score": 1.0
    }
]

class KeywordCategoryConfig(TypedDict):
    market_moving: List[str]
    urgent: List[str]
    macro_politics: List[str]
    major_tech: List[str]
    price_analysis: List[str]
    business_development: List[str]
    security_incident: List[str]

class KeywordCapConfig(TypedDict):
    market_moving: float
    macro_politics: float
    major_tech: float
    price_analysis: float
    business_development: float
    negative_event: float

class ScoringWeights(TypedDict):
    base_score: float
    keyword_categories: KeywordCategoryConfig
    keyword_caps: KeywordCapConfig
    macro_entities: List[str]
    non_core_penalty_multiplier: float
    penalty_exempt_categories: List[str]
    major_tokens: List[str]
    major_exchanges: List[str]
    time_decay_lambda_per_hour: float
    cluster_trend_bonus: float
    topic_novelty_penalty: float
    baseline_keyword_freqs: Dict[str, float]

SCORING_WEIGHTS: ScoringWeights = {
    # Điểm sàn mặc định cho mọi bài báo
    "base_score": 3.0,
    
    # Hàm mũ y=e^(-lambda*x). Lambda 0.035 nghĩa là sau 20h điểm giảm còn 1/2.
    "time_decay_lambda_per_hour": 0.035, 
    
    # Điểm cộng thêm cho tính lan truyền (Trend) dựa trên số tờ báo cùng đưa 1 tin (Cluster Size)
    "cluster_trend_bonus": 1.0,
    
    # Từ khóa chia làm các rổ. Bài tính Max-cap của từng rổ cộng lại.
    "keyword_categories": {
        "market_moving": [
            "regulation", "regulatory", "etf approval", "spot etf", "etf rejection", "bitcoin etf",
            "halving", "bitcoin halving", "legal tender", "cbdc", "central bank digital currency",
            "institutional adoption", "crypto adoption", "mica", "crypto tax", "taxation", "compliance", "crackdown", "framework"
        ],
        "macro_politics": [
            "bill", "legislation", "sec", "regulator", "government", "policy", "fed", "inflation", 
            "cpi", "rate", "powell", "fomc", "interest rates", "non-farm payrolls", "treasury", 
            "white house", "election", "dollar index", "dxy", "ppi", "gdp", "feds", "regulators", 
            "senate", "congress"
        ],
        "major_tech": ["mainnet", "protocol", "network", "roadmap", "hard fork", "soft fork"],
        "price_analysis": [
            "price", "surge", "surges", "rally", "rallies", "climb", "climbs", "jump", "jumps", "soar", "soars", "drop", "drops", "slide", "slides", "plunge", "plunges", "dips", "dip", "pump", "dumps", "dumping", "pumped", "dumped", "bullish", "bearish",
            "analyst says", "experts believe", "could surge", "might rally", "market sentiment", "investors expect", "data suggests", "technical setup", "chart pattern", "resistance", "support", "breakout", "break down",
            "trendline", "moving average", "EMA", "SMA", "Take It To", "bottom", "top", "on track to", "Crypto Today", "The Daily", "hits", "hit", "bears", "bear", "bulls", "bull",
            "RSI", "MACD", "overbought", "oversold",
            "fibonacci", "retracement",
            "consolidation", "accumulation", "distribution",
            "double top", "double bottom",
            "head and shoulders", "inverse head and shoulders",
            "cup and handle", "ascending triangle", "descending triangle",  "on track to", "set to", "poised to", "targeting", "toward $", "could hit", "will hit", "can reach",
            "growth", "prospects", "valuation", "test", "loses", "retiree", "individual", "consumer", "retail", "opinion", "editorial", "sentiment", "expert scam",
            "stuck at", "hovers", "reclaims", "targets", "to $", "at $", "predicts", "outlook", "forecast", "expert warns", "won't hold", "falls toward"
        ],
        "business_development": [
            "funding", "investment", "invest", "invests", "invested", "raises", "raise", "raising", "venture funding", "series a", "series b", "series c",
            "acquire", "acquisition", "merger", "buyout", "partnership", "collaboration", "integration",
            "launch", "launches", "launched", "mainnet launch", "testnet launch", "token launch",
            "buyback", "treasury purchase", "token burn", "burn", "supply reduction", "staking launch"
        ],
        "negative_event": [
            # Security
            "hack", "hacks", "hacked", "exploit", "exploits", "exploited", "attack", "attacks", "attacked", "rug pull", "scam", "breach", "security incident", "vulnerability", "fraud", "theft", "embezzle", "probe",
            # Legal & Regulatory Actions
            "lawsuit", "sues", "sued", "charges", "indictment", "court", "fine", "settlement", "sanction", "ban", "investigation", "enforcement", "subpoena", "freeze funds", "arrest", "arrested",
            # Operational Failures & Bearish Token Mics
            "withdrawal halt", "trading halt", "suspend trading", "halt withdrawals", "outage", "downtime", "system failure", "delist", "delisting",
            "token unlock", "unlock", "staking unlock", "inflation change"
        ]
    },
    
    # Điểm Trần (Cap) của từng rổ để tránh lạm phát
    "keyword_caps": {
        "market_moving": 8.0,
        "macro_politics": 9.0,
        "major_tech": 6.0,
        "price_analysis": -18.0,
        "business_development": 10.0,
        "negative_event": 10.0
    },
    
    "major_tokens": [
        "BTC", "Bitcoin", "ETH", "Ethereum", "BNB", "SOL", "Solana", "XRP", "Ripple", "DOGE", "Dogecoin", 
        "ADA", "Cardano", "AVAX", "Avalanche", "TRX", "Tron", "DOT", "Polkadot", "LINK", "Chainlink", 
        "MATIC", "POL", "Polygon", "SHIB", "Shiba Inu", "TON", "Toncoin", "ICP", "Internet Computer", 
        "BCH", "Bitcoin Cash", "Near Protocol", "LTC", "Litecoin", "UNI", "Uniswap", "APT", "Aptos", 
        "ARB", "Arbitrum", "OP", "Optimism", "SUI", "INJ", "Injective", "ATOM", "Cosmos", "FTM", "Fantom", 
        "AAVE", "MKR", "Maker", "OKB", "HYPE", "Hyperliquid", "PEPE", "WIF", "dogwifhat", "KAS", "Kaspa", 
        "XLM", "Stellar", "XMR", "Monero", "RNDR", "Render", "TAO", "Bittensor", "FIL", "Filecoin", 
        "STX", "Stacks", "IMX", "Immutable", "MNT", "Mantle", "VET", "VeChain", "FLOKI", "LDO", "Lido", 
        "JUP", "Jupiter", "TIA", "Celestia", "SEI", "CRO", "Cronos", "HBAR", "Hedera", "WLD", "Worldcoin", 
        "BGB", "PYTH", "GRT", "The Graph", "ENA", "Ethena", "ONDO", "THETA", "AR", "Arweave"
    ],
    "major_exchanges": ["Binance", "Coinbase", "OKX", "Kraken", "Bybit", "KuCoin", "Bitfinex", "Gate", "Gate.io", "Huobi", "HTX", "Crypto.com", "Gemini", "Bitstamp", "MEXC", "Bitget", "BitMEX", "Upbit", "BingX"],
    
    # Thực thể vĩ mô (SEC, Fed...) bổ trợ cho Token & Sàn
    "macro_entities": [
        "SEC", "Fed", "FOMC", "Powell", "Trump", "Musk", "Vitalik", "BlackRock", "Fidelity", "MicroStrategy", "Saylor", 
        "Tether", "USDT", "USDC", "Circle"
    ],
    
    # Cấu hình Phạt cho tin không có Core Entity (Áp dụng cho rổ Security/Business/Tech)
    "non_core_penalty_multiplier": 0.4, # Giữ lại 40% điểm (Phạt 60%)
    "penalty_exempt_categories": ["market_moving", "macro_politics"], # Các rổ miễn trừ phạt
    
    # [NEW] Two-Layer Speculation Filter: Tự động loại bỏ tin "thầy dùi" dự đoán giá ảo
    "SPECULATION_HARD_REJECT_PATTERN": r"(?i)(price\s+prediction|price\s+target|forecast\s+price|market\s+outlook|will\s+reach|\bscore\b.*\bprediction\b|forecast.*\d+\$|\bpump and dump\b|\bponzi\b|\bshitcoin\b)",
    "SPECULATION_SOFT_PENALTY_SCORE": -12.0,
    
    # [MODIFIED V4.2] Chỉ bắt tiền triệu >= 50M, hoặc tiền tỷ
    "CAPITAL_FLOW_REGEX": r"(?i)\$?\b(?:(?:[5-9][0-9]|[1-9][0-9]{2,})\s*(?:million|m)|[0-9]+(?:\.[0-9]+)?\s*(?:billion|trillion|b|t))\b|\b[1-9][0-9]{2,}\s*(?:BTC|ETH|SOL)\b",
    "CAPITAL_FLOW_BONUS": 2.0,
    
    # Phạt bài viết chung chủ đề với bài xếp trên nó (Diversity Check ở Phase 4)
    # 0.4 nghĩa là phạt mất 60% tổng điểm
    "topic_novelty_penalty": 0.4,
    
    # Tần suất gốc cấy sẵn cho Cold-Start AI (V2) - Cập nhật từ Scan Thực tế
    "baseline_keyword_freqs": {
        "bitcoin": 75.0,
        "btc": 35.0,
        "ethereum": 20.0,
        "eth": 20.0,
        "xrp": 30.0,
        "sol": 15.0,
        "solana": 10.0,
        "etf": 20.0,
        "trump": 15.0,
        "coinbase": 15.0,
        "binance": 10.0,
        "sec": 10.0,
        "tether": 10.0,
        "shiba inu": 15.0,
        "dogecoin": 10.0,
        "doge": 10.0,
        "ripple": 10.0,
        "cardano": 10.0,
        "hack": 5.0,
        "scam": 5.0,
        "exploit": 5.0,
        "attacks": 5.0,
        "bankrupt": 5.0
    }
}

# --- CẤU HÌNH CHO PHASE 5: TÓM TẮT & TWEET ---

# Khai báo sẵn danh sách API Keys nếu có (tránh rỗng)
_openai_keys = [k for k in [os.environ.get(f"OPENAI_API_KEY_{i}") for i in range(1, 10)] + [os.environ.get("OPENAI_API_KEY")] if k]
_gemini_keys = [k for k in [os.environ.get(f"GEMINI_API_KEY_{i}") for i in range(1, 10)] + [os.environ.get("GEMINI_API_KEY")] if k]

LLM_CONFIG = {
    # Chọn nhà cung cấp: "openai" hoặc "gemini"
    "active_provider": os.environ.get("LLM_PROVIDER", "gemini").lower(),
    
    "openai": {
        "api_keys": _openai_keys if _openai_keys else ["dummy_key_for_test"],
    },
    
    "gemini": {
        "api_keys": _gemini_keys if _gemini_keys else ["dummy_key_for_test"],
    },
    
    "lane_models": {
        "RSS": ["gemini-2.5-flash", "gemma-3-27b-it"],        # Fallback hierarchy for RSS
        "EXPRESS": ["gemma-3-27b-it"]                         # Fixed model for Express
    },
    
    "lane_timeouts": {
        "RSS": 15,       # Seconds: Standard timeout for RSS pool
        "EXPRESS": 8     # Seconds: Strict timeout to prevent blocking listener
    },
    
    "max_tokens": 150,
    "temperature": 0.3, # Giữ temperature thấp để tránh AI "ảo giác" (hallucination)
    "max_retries": 2  # Hard limit per pipeline
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
        "You rewrite breaking news for a Telegram crypto news channel.\n"
        "\n"
        "Style rules:\n"
        "- Vietnamese only. Translate 'cryptocurrency' as 'tiền mã hóa'.\n"
        "- Use a neutral, professional news tone.\n"
        "- Headline must be factual, short, and descriptive.\n"
        "- Do NOT use sensational words such as: 'TIN NÓNG', 'KHẨN CẤP', 'BREAKING', 'ALERT', 'CỰC NÓNG'.\n"
        "- Focus only on the core event.\n"
        "- Be concise and clear.\n"
        "- Do NOT invent facts.\n"
        "\n"
        "Market context rule:\n"
        "- If the news is crypto-related, add one short possible market implication.\n"
        "- Use cautious wording such as: 'có thể', 'thị trường có thể phản ứng'.\n"
        "- If unrelated to crypto markets -> IMPACT: 'Chưa rõ tác động'.\n"
        "\n"
        "Output format (strict):\n"
        "HEADLINE: <short factual headline>|||SUMMARY: <1-2 concise sentences>|||IMPACT: <market implication or 'Chưa rõ tác động'>"
    ),
    "RSS": (
        "You are a neutral macro and technology news reporter for the crypto ecosystem.\n"
        "Analyze the provided article (title + summary).\n"
        "\n"
        "Writing rules:\n"
        "- Vietnamese only. Translate 'cryptocurrency' as 'tiền mã hóa'.\n"
        "- Use ONLY the information from the article. Do NOT invent facts.\n"
        "- Neutral journalistic tone. Event-focused.\n"
        "- Do NOT speculate about price movements.\n"
        "- Do NOT give investment advice.\n"
        "- Focus on explaining the key facts of the event.\n"
        "\n"
        "Formatting rules:\n"
        "- HEADLINE must be SHORT and in FULL UPPERCASE.\n"
        "- Write 3–5 bullet points.\n"
        "- Each bullet point explains ONE key piece of information.\n"
        "- Each bullet should be 1–3 sentences.\n"
        "- Use the bullet symbol '🔷'.\n"
        "- Do NOT add commentary or speculation.\n"
        "\n"
        "Hashtag rules:\n"
        "- Add 2–3 hashtags at the end of the post.\n"
        "- Hashtags must be in English.\n"
        "- Use short ecosystem or topic tags (example: #Bitcoin #Ethereum #CryptoRegulation #DeFi #OilMarket).\n"
        "\n"
        "Output format (strict):\n"
        "HEADLINE\n"
        "\n"
        "🔷 <bullet point 1>\n"
        "\n"
        "🔷 <bullet point 2>\n"
        "\n"
        "🔷 <bullet point 3>\n"
        "\n"
        "🔷 <bullet point 4 if needed>"
        "|||HASHTAGS: <1-3 tags>"
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
    "chat_ids": {
        # Nếu có TELEGRAM_CHAT_ID_RSS trong .env thì lấy, không thì lấy chung TELEGRAM_CHAT_ID
        "RSS": os.environ.get("TELEGRAM_CHAT_ID_RSS", os.environ.get("TELEGRAM_CHAT_ID", "")),
        "EXPRESS": os.environ.get("TELEGRAM_CHAT_ID_EXPRESS", os.environ.get("TELEGRAM_CHAT_ID", ""))
    }
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
RSS_LOOP_INTERVAL = 240 * 60 # 15 minutes by default

# Thư mục chứa Data
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
