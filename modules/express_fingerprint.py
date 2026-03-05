import re
import logging
from typing import List, Set

logger = logging.getLogger("FINGERPRINT")

# Danh sách thực thể Core (Các tay to, quỹ, sàn thường xuyên bơm thổi tin tức)
STATIC_ENTITIES = {
    # Tay to Crypto
    "binance", "coinbase", "kraken", "kucoin", "okx", "bybit",
    "blackrock", "fidelity", "vanguard", "gray_scale", "grayscale", "microstrategy",
    "elon musk", "vitalik", "cz", "sbf", "saylor", "trump", "biden", "harris",
    
    # Coins/Tokens chính
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "tether", "usdt", "usdc",
    
    # Tổ chức & Vĩ mô (Tiếng Anh + Việt)
    "sec", "cftc", "fbi", "doj", "fed", "ecb", "boj", "gary gensler", "cục dự trữ", "lãi suất", "cpi", "gdp", "pce", "pmi", "nonfarm",
    "chính phủ", "chứng khoán", "hoa kỳ", "mỹ", "mĩ", "usa", "nga", "russia", "ukraine", "israel", "iran", 
    "trung quốc", "china", "hàn quốc", "bắc triều tiên", "đài loan", "taiwan",
    
    # Chiến tranh / Xung đột
    "chiến tranh", "xung đột", "tên lửa", "không kích",
    
    # Các mảng công nghệ
    "defi", "nft", "gamefi", "web3", "metaverse",
    
    # Các sàn/tổ chức cựu trào (Hay bị nhắc tên đào lại)
    "ftx", "mtgox", "mt gox", "genesis", "blockfi", "celsius"
}

def extract_fingerprints(text: str) -> List[str]:
    """
    Trích xuất các thực thể danh từ riêng (Proper Nouns) làm Fingerprint.
    - $TOKEN
    - TỪ VIẾT HOA (ALL CAPS) > 2 ký tự (Ví dụ: SEC, ETF, BTC)
    - CamelCase (Tên riêng: Elon Musk, BlackRock)
    - Static Entities list
    """
    fingerprints: Set[str] = set()
    
    # Chuẩn hóa để check danh sách tĩnh dễ dàng
    lower_text = text.lower()
    
    # 1. Quét Static Entities
    for entity in STATIC_ENTITIES:
        # Regex \b để đảm bảo match đúng ranh giới từ (vd: không lấy 'sec' trong 'second')
        if re.search(r'\b' + re.escape(entity) + r'\b', lower_text):
            fingerprints.add(entity)
            
    # 2. Quét $TOKEN (VD: $BTC, $ETH, $DOGE)
    tokens = re.findall(r'\$[A-Za-z0-9]+', text)
    for t in tokens:
        fingerprints.add(t.lower().replace('$', '')) # Gỡ bỏ dấu $ để dễ normalize
        
    # 3. Quét ALL CAPS (Từ viết hoa hoàn toàn, dài 3-8 ký tự)
    # Loại trừ các từ phổ thông viết hoa nhấn mạnh như THE, AND, BUT, BREAKING, URGENT, JUST, IN
    common_caps = {
        "THE", "AND", "BUT", "FOR", "WITH", "BREAKING", "URGENT", "JUST", "IN", "UPDATE", "NEW",
        "OMG", "LOL", "LMAO", "CEO", "CTO", "CFO", "ASAP", "USA", "USD", "EUR", "GBP", "VND", 
        "FOMO", "FUD", "NOW", "OUT", "OFF", "ON", "LIVE", "THIS", "THAT", "HERE", "MINT", "ATH", "ATL"
    }
    caps_matches = re.findall(r'\b[A-Z]{3,8}\b', text)
    for cap in caps_matches:
        if cap not in common_caps:
            fingerprints.add(cap.lower())
            
    # 4. Quét CamelCase/Title Case cơ bản (Tên người/tổ chức viết hoa chữ cái đầu liên tiếp)
    # Vd: "Elon Musk", "BlackRock", "Federal Reserve"
    # Pattern: Hai từ trở lên, viết hoa nốt đầu, nối với nhau bằng khoảng trắng
    title_case_matches = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
    for tc in title_case_matches:
        fingerprints.add(tc.lower())
        
    # Sắp xếp theo alphabet để generate fingerprint chuỗi (Signature) có tính deterministic
    sorted_fingerprints = sorted(list(fingerprints))
    
    # Log the result
    signature_str = " | ".join(sorted_fingerprints)
    if sorted_fingerprints:
         logger.info(f"🧬 [FINGERPRINT EXTRACTED]: {signature_str}")
    else:
         logger.info(f"🧬 [FINGERPRINT EXTRACTED]: (No strong entities found)")
         
    return sorted_fingerprints

def generate_fingerprint_signature(fingerprints: List[str]) -> str:
    """Ghép mảng fingerprint thành 1 signature string duy nhất để lưu DB."""
    return "||".join(fingerprints)
