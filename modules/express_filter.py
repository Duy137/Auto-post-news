import logging
import re
from typing import Dict, Tuple

logger = logging.getLogger("EXPRESS_FILTER")

# Từ khóa CỐT LÕI (Luôn điểm cao, qua luôn màng lọc)
CRYPTO_CORE_WEIGHTS: Dict[str, float] = {
    # Hack/Exploit
    r'\bhack(ed)?\b': 30,
    r'\bbị hack\b': 30,
    r'\bexploit(ed)?\b': 30,
    r'\btấn công\b': 30,
    r'\bl[ỗổ]? hổng\b': 30,
    r'\bstolen\b': 30,
    r'\bdrain(ed)?\b': 30,
    r'\brút ruột\b': 30,
    r'\b51% attack\b': 30,
    r'\brug pull(ed)?\b': 30,
    r'\blừa đảo\b': 30,
    
    # Operations
    r'\bbankrupt(cy)?\b': 30,
    r'\bphá sản\b': 30,
    r'\bchặn rút\b': 30,
    r'\bđóng băng\b': 30,
    r'\b(suspend|halt).*withdraw(al|s)?\b': 30,
    r'\bsập sàn\b': 30,
    
    # Regulations & Core Crypto Events
    r'\betf\b': 30,
    r'\bsec\b': 30,
    r'\bapprov(ed|al)?\b': 30,
    r'\bduyệt\b': 30,
    r'\bthông qua\b': 30,
    r'\blisting\b': 30,
    r'\bniêm yết\b': 30,
    r'\blên sàn\b': 30,
    r'\bdelist(ing|ed)?\b': 30,
    r'\bhủy niêm yết\b': 30,
    r'\bxóa khỏi sàn\b': 30,
    r'\ba[ií]rdrop\b': 20,
    r'\btrả thưởng\b': 20,
    r'\bmainnet\b': 30,
    r'\bupgrade\b': 20.0,
    r'\bnâng cấp\b': 20.0,
    r'\bhard fork\b': 20.0,
    r'\bphân nhánh\b': 20.0,
    r'\bhalving\b': 20.0,
    r'\bchia đôi\b': 20.0,
    r'\bpartnership\b': 20.0,
    r'\bhợp tác\b': 20.0,
    r'\bintegrate(d)?\b': 20.0,
    r'\btích hợp\b': 20.0,
    
    # SPAM / JUNK Penalties
    r'\b(giveaway|join|subscribe)\b': -50.0,
    r'\btham gia ngay\b': -50.0,
    r'\bnhận quà\b': -50.0,
}

# Các sự kiện VĨ MÔ & ĐỊA CHÍNH TRỊ (Các từ kinh tế đủ điểm qua chốt, các từ địa chính trị vẫn cần mix thêm Entity)
MACRO_GEOPOLITICS_WEIGHTS: Dict[str, float] = {
    # Kinh tế vĩ mô (Tăng lên >= 15.0 để qua màng lọc độc lập)
    r'\bcpi\b': 20.0,
    r'\bpce\b': 20.0,
    r'\bppi\b': 20.0,
    r'\blạm phát\b': 20.0,
    r'\binflation\b': 20.0,
    r'\blãi suất\b': 20.0,
    r'\binterest rate(s)?\b': 20.0,
    r'\bgdp\b': 20.0,
    r'\bpmi\b': 20.0,
    r'\bthất nghiệp\b': 20.0,
    r'\bunemployment\b': 20.0,
    r'\bnonfarm\b': 20.0,
    r'\bpayroll(s)?\b': 20.0,
    r'\bviệc làm\b': 20.0,
    r'\bkích thích\b': 20.0,
    r'\bstimulus\b': 20.0,
    r'\bbơm tiền\b': 20.0,
    r'\bin tiền\b': 20.0,
    r'\bprint(ing)? money\b': 20.0,
    
    # Chính sách
    r'\bcấm\b': 20.0,
    r'\bban\b': 20.0,
    r'\b(luật|quy định|regulation|policy)\b': 20.0,
    r'\bcấm vận\b': 20.0,
    r'\bsanction(s)?\b': 20.0,
    
    # Địa chính trị (Giữ điểm 10.0 để chờ ghép cặp Entity -> 60.0 điểm)
    r'\bbầu cử\b': 20.0,
    r'\belection(s)?\b': 20.0,
    r'\btổng thống\b': 20.0,
    r'\bpresident\b': 20.0,
    r'\bthủ tướng\b': 20.0,
    r'\bchiến tranh\b': 20.0,
    r'\bwar\b': 20.0,
    r'\bxung đột\b': 20.0,
    r'\bconflict\b': 20.0,
    r'\btên lửa\b': 20.0,
    r'\bmissile(s)?\b': 20.0,
    r'\bkhông kích\b': 20.0,
    r'\bairstrike(s)?\b': 20.0,
    r'\bcăng thẳng\b': 20.0,
    r'\btension(s)?\b': 20.0,
    r'\bquân đội\b': 20.0,
    r'\bmilitary\b': 20.0,
    r'\đối thoại\b': 20.0,
    r'\tuyên bố\b': 20.0,
}

# CÁC QUỐC GIA, TỔ CHỨC VÀ ĐỊNH CHẾ TÀI CHÍNH (Tăng lên 10.0 theo ý Sếp)
ENTITIES_WEIGHTS: Dict[str, float] = {
    # Các tổ chức tài chính hàng đầu (Qua chốt độc lập)
    r'\bfed\b': 20.0,
    r'\bfomc\b': 20.0,
    r'\bcục dự trữ\b': 20.0,
    r'\becb\b': 20.0,
    r'\bboj\b': 20.0,
    
    # Quốc gia và Tổ chức (10.0)
    r'\bmỹ\b': 10.0, r'\bmĩ\b': 10.0, r'\busa\b': 10.0, r'\bus\b': 10.0, r'\bhoa kỳ\b': 10.0,
    r'\bnga\b': 10.0, r'\brussia\b': 10.0, r'\bputin\b': 10.0,
    r'\bukraine\b': 10.0, r'\bzelensky\b': 10.0,
    r'\bisrael\b': 10.0, r'\biran\b': 15.0,
    r'\bpalestine\b': 10.0, r'\bgaza\b': 10.0, r'\bhamas\b': 10.0, r'\bhezbollah\b': 10.0,
    r'\blebanon\b': 10.0, r'\bli-băng\b': 10.0,
    r'\bsyria\b': 10.0, r'\byemen\b': 10.0, r'\bhouthi\b': 10.0, r'\biraq\b': 10.0,
    r'\btrung đông\b': 15.0, r'\bmiddle east\b': 10.0, r'\bchâu á\b': 10.0, r'\basia\b': 10.0,
    r'\btrung quốc\b': 10.0, r'\bchina\b': 10.0, r'\bbắc kinh\b': 10.0, r'\bbeijing\b': 10.0,
    r'\bhàn quốc\b': 10.0, r'\bsouth korea\b': 10.0, r'\beurozone\b': 10.0, r'\bchâu âu\b': 10.0,
    r'\bbắc triều tiên\b': 10.0, r'\bnorth korea\b': 10.0, r'\btriều tiên\b': 10.0, r'\bbình nhưỡng\b': 10.0,
    r'\bđài loan\b': 10.0, r'\btaiwan\b': 10.0,
    r'\bnhật bản\b': 10.0, r'\bjapan\b': 10.0,
    r'\bpháp\b': 10.0, r'\bfrance\b': 10.0, r'\bđức\b': 10.0, r'\bgermany\b': 10.0, r'\banh\b': 10.0, r'\buk\b': 10.0,
    r'\bliên minh châu âu\b': 10.0, r'\beu\b': 10.0,
    r'\bnato\b': 10.0,
    r'\bliên hợp quốc\b': 10.0, r'\bun\b': 10.0,
}

# Ngưỡng điểm tối thiểu để tin được coi là có giá trị và đưa cho LLM xử lý
EXPRESS_SCORE_THRESHOLD = 15.0
SYNERGY_BONUS = 50.0  # Điểm cộng thêm khi có cả Macro và Entity

def process_dict(text: str, weight_dict: Dict[str, float]) -> Tuple[float, dict]:
    """Helper để quét dictionary và tính điểm."""
    score = 0.0
    matches_found = {}
    for pattern, weight in weight_dict.items():
        matches = set(re.findall(pattern, text))
        if matches:
            display_name = pattern.strip(r'\b')
            score += weight
            matches_found[display_name] = weight
    return score, matches_found

def score_express_message(text: str) -> Tuple[bool, float, dict]:
    """
    Chấm điểm nội dung tin Telegram dựa trên Context-Aware Keyword Weights.
    Trả về: (is_passed, total_score, matched_keywords)
    """
    total_score = 0.0
    matched_keywords = {}
    normalized_text = text.lower()
    
    # 1. Quét Core Crypto
    core_score, core_matches = process_dict(normalized_text, CRYPTO_CORE_WEIGHTS)
    total_score += core_score
    matched_keywords.update(core_matches)
    
    # 2. Quét Macro Geopolitics
    macro_score, macro_matches = process_dict(normalized_text, MACRO_GEOPOLITICS_WEIGHTS)
    total_score += macro_score
    matched_keywords.update(macro_matches)
    
    # 3. Quét Entities
    entity_score, entity_matches = process_dict(normalized_text, ENTITIES_WEIGHTS)
    total_score += entity_score
    matched_keywords.update(entity_matches)
    
    # 4. Kiểm tra Synergy Bonus (Bối cảnh 2 yếu tố)
    has_macro = len(macro_matches) > 0
    has_entity = len(entity_matches) > 0
    
    if has_macro and has_entity:
        total_score += SYNERGY_BONUS
        matched_keywords['SYNERGY_BONUS (Macro+Entity)'] = SYNERGY_BONUS
        
    # Bổ sung điểm thưởng cho các tín hiệu đặc biệt
    if '!' in text:
        total_score += 5.0
        matched_keywords['has_exclamation'] = 5.0
        
    is_passed = total_score >= EXPRESS_SCORE_THRESHOLD
    
    if is_passed:
        logger.info(f"✅ PASSED Filter | Score: {total_score} >= {EXPRESS_SCORE_THRESHOLD} | Matches: {matched_keywords}")
    else:
        logger.info(f"❌ FAILED Filter | Score: {total_score} < {EXPRESS_SCORE_THRESHOLD} | Matches: {matched_keywords}")
        
    return is_passed, total_score, matched_keywords
