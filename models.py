import hashlib
from typing import TypedDict, Optional

class ScoreDetail(TypedDict, total=False):
    base_score: float
    adaptive_keyword_score: float
    editorial_verb_score: float
    cross_source_momentum_score: float
    source_credibility: float
    source_latency_advantage: float
    topic_novelty_multiplier: float
    time_decay_multiplier: float
    viral_potential: float
    shock_score: float
    editorial_score: float
    total_score: float

class Article(TypedDict):
    id: str  # Deterministic string (SHA1 hash)
    title: str
    link: str  # Dùng Canonical Link để Tweet
    raw_source_url: str  # Link gốc dính Tracking Params
    summary: str
    published_ts: int # Lưu hành bằng unix timestamp (chuẩn Time)
    source_name: str
    
    # Các trường mở rộng (Optional) cho các phase sau
    score: Optional[float]
    score_detail: Optional[ScoreDetail]
    structured_content: Optional[dict]  # HEADLINE, SUMMARY, HASHTAGS
    tweet_content: Optional[str]  # Chứa nội dung raw fallback nếu có
    event_root_id: Optional[str]  # Định danh rễ sự kiện cho Topic Persistence

class PlatformResult(TypedDict):
    success: bool
    post_id: Optional[str]
    error: Optional[str]

class PublishResult(TypedDict):
    article_id: str
    results: dict[str, PlatformResult] # key: "twitter", "telegram", "facebook"
    posted_timestamp: Optional[int]

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def normalize_url(url: str) -> str:
    """
    Chuẩn hóa URL để tránh duplicate do tracking params:
    - Lowercase domain
    - Bỏ trailing slash
    - Bỏ fragment (#)
    - Xóa các tracking query params (utm_, fbclid, vv)
    """
    if not url:
        return ""
        
    parsed = urlparse(url.strip())
    
    # 1. Lowercase scheme & netloc (domain)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    # 2. Xóa trailing slash ở cuối path
    path = parsed.path
    if path.endswith('/') and len(path) > 1:
        path = path[:-1]
        
    # 3. Lọc bỏ các params rác
    queries = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_queries = [
        (k, v) for k, v in queries 
        if not k.lower().startswith(('utm_', 'fbclid', 'ref', 'source'))
    ]
    
    # Sort query params để luôn ra cùng một string cho cùng bộ params
    filtered_queries.sort()
    new_query = urlencode(filtered_queries)
    
    # Bỏ qua fragment (parsed.fragment)
    normalized = urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
    return normalized

def generate_article_id(url: str) -> str:
    """Generate deterministic SHA1 hash from NORMLIZED canonical link."""
    clean_url = normalize_url(url)
    return hashlib.sha1(clean_url.encode('utf-8')).hexdigest()
