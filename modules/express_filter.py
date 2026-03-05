import logging
import re
from typing import Dict, Tuple

logger = logging.getLogger("EXPRESS_FILTER")

# Từ khóa trọng số (Weight Mapping)
# Điểm số có thể âm để phạt các tin giả/tin rác
KEYWORD_WEIGHTS: Dict[str, float] = {
    # Tích cực / Quan trọng cao (Toàn cầu)
    r'\bhack(ed)?\b': 100.0,
    r'\bbị hack\b': 100.0,
    r'\bexploit(ed)?\b': 100.0,
    r'\btấn công\b': 80.0,
    r'\bl[ỗổ]? hổng\b': 80.0,
    
    r'\bbankrupt(cy)?\b': 80.0,
    r'\bphá sản\b': 80.0,
    r'\bchặn rút\b': 70.0,
    r'\bđóng băng\b': 70.0,
    r'\b(suspend|halt).*withdraw(al|s)?\b': 70.0,
    
    r'\betf\b': 50.0,
    r'\bsec\b': 50.0,
    
    r'\bapprov(ed|al)?\b': 30.0,
    r'\bduyệt\b': 30.0,
    r'\bthông qua\b': 30.0,
    
    r'\blisting\b': 30.0,
    r'\bniêm yết\b': 30.0,
    r'\blên sàn\b': 30.0,
    
    r'\bdelist(ing|ed)?\b': 40.0,
    r'\bhủy niêm yết\b': 40.0,
    r'\bxóa khỏi sàn\b': 40.0,
    
    r'\ba[ií]rdrop\b': 10.0,
    r'\btrả thưởng\b': 10.0,
    
    r'\bmainnet\b': 20.0,
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
    
    r'\bstolen\b': 80.0,
    r'\bdrain(ed)?\b': 80.0,
    r'\brút ruột\b': 80.0,
    r'\b51% attack\b': 100.0,
    r'\brug pull(ed)?\b': 100.0,
    r'\blừa đảo\b': 80.0,
    r'\bsập sàn\b': 100.0,
    
    # Kinh tế Vĩ Mô (Macro) / Chính trị (Politics)
    # Lạm phát & Lãi suất
    r'\bcpi\b': 60.0,
    r'\bpce\b': 60.0,
    r'\bppi\b': 50.0,
    r'\blạm phát\b': 60.0,
    r'\binflation\b': 60.0,
    r'\blãi suất\b': 60.0,
    r'\binterest rate(s)?\b': 60.0,
    
    # Định chế tài chính
    r'\bfed\b': 50.0,
    r'\bfomc\b': 50.0,
    r'\bcục dự trữ\b': 40.0,
    r'\becb\b': 40.0,
    r'\bboj\b': 40.0,
    
    # Dữ liệu kinh tế (Employment, GDP, PMI)
    r'\bgdp\b': 40.0,
    r'\bpmi\b': 40.0,
    r'\bthất nghiệp\b': 40.0,
    r'\bunemployment\b': 40.0,
    r'\bnonfarm\b': 40.0,
    r'\bpayroll(s)?\b': 40.0,
    r'\bviệc làm\b': 40.0,
    
    # Bầu cử & Lãnh đạo
    r'\bbầu cử\b': 50.0,
    r'\belection(s)?\b': 50.0,
    r'\btổng thống\b': 40.0,
    r'\bpresident\b': 30.0,
    r'\bthủ tướng\b': 30.0,
    
    # Chiến tranh & Địa chính trị (Geopolitics)
    r'\bchiến tranh\b': 80.0,
    r'\bwar\b': 80.0,
    r'\bxung đột\b': 70.0,
    r'\bconflict\b': 70.0,
    r'\btên lửa\b': 70.0,
    r'\bmissile(s)?\b': 70.0,
    r'\bkhông kích\b': 60.0,
    r'\bairstrike(s)?\b': 60.0,
    r'\bcăng thẳng\b': 40.0,
    r'\btension(s)?\b': 40.0,
    r'\bquân đội\b': 40.0,
    r'\bmilitary\b': 40.0,
    
    # Quốc gia (Trọng điểm)
    r'\bmỹ\b': 30.0,
    r'\bmĩ\b': 30.0,
    r'\busa\b': 30.0,
    r'\bus\b': 30.0,
    r'\bnga\b': 40.0,
    r'\brussia\b': 40.0,
    r'\bukraine\b': 40.0,
    r'\bisrael\b': 50.0,
    r'\biran\b': 50.0,
    r'\btrung quốc\b': 30.0,
    r'\bchina\b': 30.0,
    r'\bhàn quốc\b': 30.0,
    r'\bsouth korea\b': 30.0,
    r'\bbắc triều tiên\b': 40.0,
    r'\bnorth korea\b': 40.0,
    r'\bđài loan\b': 30.0,
    r'\btaiwan\b': 30.0,
    
    # Chính sách, Lệnh cấm
    r'\bcấm\b': 50.0,
    r'\bban\b': 50.0,
    r'\b(luật|quy định|regulation|policy)\b': 30.0,
    r'\bcấm vận\b': 60.0,
    r'\bsanction(s)?\b': 60.0,
    
    # Tiền tệ & Thanh khoản
    r'\bkích thích\b': 40.0,
    r'\bstimulus\b': 40.0,
    r'\bbơm tiền\b': 40.0,
    r'\bin tiền\b': 40.0,
    r'\bprint(ing)? money\b': 40.0,
    
    # Kèo mõm, suy đoán (Phạt điểm)
    r'\brumor(s)?\b': -20.0,
    r'\btin đồn\b': -20.0,
    r'\b(think|believe)s?\b': -10.0,
    r'\bnghĩ rằng\b': -10.0,
    r'\b(could|might|maybe)\b': -5.0,
    r'\bcó thể\b': -5.0,
    r'\b(probably)\b': -5.0,
    r'\bnhiều khả năng\b': -5.0,
    
    # Quảng cáo lộ liễu
    r'\b(giveaway|join|subscribe)\b': -50.0,
    r'\btham gia ngay\b': -50.0,
    r'\bnhận quà\b': -50.0,
}

# Ngưỡng điểm tối thiểu để tin được coi là có giá trị và đưa cho LLM xử lý
EXPRESS_SCORE_THRESHOLD = 15.0

def score_express_message(text: str) -> Tuple[bool, float, dict]:
    """
    Chấm điểm nội dung tin Telegram dựa trên Keyword Weights.
    Trả về: (is_passed, total_score, matched_keywords)
    """
    total_score = 0.0
    matched_keywords = {}
    
    # Chuẩn hóa: lowercase để dễ match
    normalized_text = text.lower()
    
    for pattern, weight in KEYWORD_WEIGHTS.items():
        # Tìm tất cả những chỗ match regex
        # Dùng set() để lỡ nó nhắc từ "hack" 3 lần thì mình chỉ tính điểm 1 lần (Tránh cố ý nhồi nhét keyword)
        matches = set(re.findall(pattern, normalized_text))
        
        if matches:
            # Chọn đại diện 1 match để log
            matched_str = list(matches)[0] 
            # Nếu regex là group e.g (ed)? nó có thể trả về string rỗng cho match, lấy pattern làm tên
            display_name = pattern.strip(r'\b')
            
            total_score += weight
            matched_keywords[display_name] = weight
            
    # Bổ sung điểm thưởng cho các tín hiệu đặc biệt (Ví dụ có dấu chấm than, viết HOA nhiều báo hiệu tin giật gân)
    if '!' in text:
        total_score += 5.0
        matched_keywords['has_exclamation'] = 5.0
        
    is_passed = total_score >= EXPRESS_SCORE_THRESHOLD
    
    if is_passed:
        logger.info(f"✅ PASSED Filter | Score: {total_score} >= {EXPRESS_SCORE_THRESHOLD} | Matches: {matched_keywords}")
    else:
        logger.info(f"❌ FAILED Filter | Score: {total_score} < {EXPRESS_SCORE_THRESHOLD} | Matches: {matched_keywords}")
        
    return is_passed, total_score, matched_keywords
