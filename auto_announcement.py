import os
import time
import datetime
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------
# AUTO ANNOUNCEMENT BOT (WEEKLY SCHEDULE)
# ---------------------------------------------------------

# 1. Tải Biến Môi Trường
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("❌ LỖI: Không tìm thấy TELEGRAM_BOT_TOKEN trong file .env")
    exit(1)

# Xử lý múi giờ Việt Nam (GMT+7) tránh lệch giờ trên máy chủ Railway (UTC)
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

# Hàm hỗ trợ lấy danh sách multi-channel từ .env cách nhau bằng dấu phẩy
def get_channels_from_env(env_key, default_fallback=""):
    val = os.getenv(env_key)
    if not val:
        val = os.getenv("TELEGRAM_CHAT_ID", default_fallback)
    if not val:
        return ["-100xxxxx"]
    return [c.strip() for c in val.split(",") if c.strip()]

# ---------------------------------------------------------
# 2. CẤU HÌNH NỘI DUNG TIN NHẮN (MESSAGES)
# ---------------------------------------------------------

MESSAGE_1 = """THAM GIA CRYPTOVN101 PREMIUM HUB: nhắn cho @zayne120
-----------------------------------------

1️⃣ <b>Quyền lợi khi trở thành CryptoVN101 Premium Member</b>
⭐️ Phân tích & định hướng thị trường
Cập nhật phân tích thị trường hằng ngày, kết hợp dữ liệu và chiến lược giao dịch được xây dựng bám sát diễn biến thực tế, giúp bạn nắm bắt xu hướng và ra quyết định hiệu quả hơn.

⭐️ Hệ thống Bot tín hiệu giao dịch
Quyền truy cập các Bot tín hiệu giao dịch dành cho <b>BTC và Altcoins</b> thanh khoản cao, được tối ưu và kiểm định với <b>tỷ lệ win cao và ổn định</b>.

⭐️ <b>Kho tài liệu kiến thức chuyên sâu</b>: <a href="https://cryptovn101.com/">https://cryptovn101.com/</a>
Sử dụng miễn phí thư viện tài liệu về <b>phân tích kỹ thuật, đầu tư, quản trị rủi ro và tư duy giao dịch</b>, được hệ thống hóa từ cơ bản đến nâng cao.

⭐️ <b>Hoàn phí giao dịch</b>
Được hoàn lại một phần phí giao dịch khi sử dụng mã giới thiệu (REF) chính thức của đội ngũ <b>CryptoVN101</b>, giúp tối ưu chi phí trong quá trình giao dịch.

2️⃣ <b>Cách thức tham gia</b>
Giao dịch thông qua ref của team CryptoVN101
Điều kiện tham gia:
- Đăng ký tài khoản mới theo link ref
- Chọn 1 trong 4 sàn sau đây: <a href="https://partner.bybit.com/b/CRYPTOVN101">Bybit</a> | <a href="https://okx.com/join/VN101">OKX</a> (Hoàn phí 10%) | <a href="https://bingxzone.com/partner/CryptoVN101">BingX</a> (Hoàn phí 10%) | <a href="https://www.mexc.com/acquisition/custom-sign-up?shareCode=mexc-3Gt3a">MEXC</a> (Hoàn phí 10%)
- Quy trình: 
   + Nạp tối thiểu 300 USDT
   + Thực hiện 1 lệnh giao dịch Future bất kỳ
   + Gửi UID tài khoản cho @cryptovn101contact để xác thực
   + Sau khi team kiểm tra hợp lệ, bạn sẽ được thêm vào Premium Hub và các bot Tele."""

MESSAGE_2 = """Xin chào anh em trong nhóm <b>CryptoVN 101 – Premium Hub</b>,

Ngay từ đầu, định hướng của team là xây dựng một cộng đồng đầu tư có tư duy đúng, kỷ luật cao và nền tảng tri thức vững chắc, tập trung vào giá trị dài hạn của thị trường tài sản số tại Việt Nam. 

📌 Trọng tâm phát triển của CryptoVN 101 bao gồm ba mũi nhọn chính: giáo dục tài sản số, tư vấn chiến lược đầu tư và giao dịch tự động hoá.

🚀 Các sản phẩm hiện tại của CryptoVN 101
1️⃣ Bot DojiScan: <a href="https://t.me/+7CjHpATnmxk5MWVl">Link Bot</a> | <a href="https://t.me/c/3116134681/149">Hướng dẫn sử dụng</a>

2️⃣ BotTradeBTC: <a href="https://t.me/+P0uEo1OsvVkyMzA1">Link Bot</a> | <a href="https://t.me/c/3116134681/369">Hướng dẫn sử dụng</a>

3️⃣ BotTradeAlts: <a href="https://t.me/+J9I-VAXj4IQxNjY1">Link Bot</a> | <a href="https://t.me/c/3116134681/408">Hướng dẫn sử dụng</a>

4️⃣ Website: <a href="https://cryptovn101.com/">cryptovn101.com</a>
Nơi tổng hợp hệ thống sách, tài liệu và kiến thức nền tảng về:
• Vĩ mô & chu kỳ thị trường
• Crypto & blockchain
• Đầu tư – giao dịch
• Quản trị vốn & tâm lý đầu tư

5️⃣ CHƯƠNG TRÌNH ĐẠI SỨ CRYPTOVN 101 – SHARED SUCCESS <a href="https://t.me/c/3116134681/473">[Link]</a>

👉 <a href="https://t.me/c/3116134681/6">Cách tham gia nhóm chat</a>

🙏 Lời cảm ơn
Team CryptoVN 101 xin gửi lời cảm ơn chân thành đến toàn bộ anh em Premium đã tin tưởng, đồng hành và đóng góp trong suốt thời gian vừa qua.

Chặng đường phía trước vẫn còn dài, và team rất mong tiếp tục nhận được sự đồng hành của anh em trên hành trình này. 🚀"""

MESSAGE_3 = """<b>[MỚI THAM GIA THỊ TRƯỜNG – NHỮNG ĐIỀU QUAN TRỌNG BẠN CẦN NHỚ]</b>

✍️ <b>VỀ NGUYÊN TẮC:</b>
1️⃣ Quản trị vốn là yếu tố sống còn. (Quan trọng nhất)
- Không vay mượn (Tài sản = 0 chưa đáng sợ bằng tài sản âm).
- Không đặt hết trứng vào một giỏ (đa dạng danh mục để giảm rủi ro).
- Không “tất tay” – luôn phải giữ vốn dự phòng.
2️⃣ Đừng tin ai
Vì thị trường có rất nhiều lừa đảo và không ai hiểu rõ hoàn cảnh của bạn hơn chính bạn.
3️⃣ Đừng để lòng tham dẫn dắt
Hầu hết những miếng phomai miễn phí đều nằm trên bẫy chuột.
4️⃣ Làm giàu kiến thức trước khi làm giàu tài sản.


✅ <b>VỀ CHIẾN LƯỢC:</b>
👉  Phần lớn vốn nên hold Spot – đầu tư dài hạn theo chu kỳ thị trường (ví dụ: phân bổ 80% vốn). -> Đây là nền tảng an toàn nhất để tồn tại và phát triển
Trong dài hạn, quy mô thị trường sẽ ngày càng mở rộng.
👉 Phần nhỏ vốn để Trading hoặc trải nghiệm các cách kiếm tiền khác trên thị trường (ví dụ: 20% vốn). -> Đây là thứ rủi ro nhưng giúp bạn lên kinh nghiệm và biết đâu bạn gặp may mắn...
Trong ngắn hạn, thị trường là trò chơi tổng bằng 0
Có những người chơi có lợi thế, nhưng đó có phải là bạn?

⚠️ <b>LƯU Ý:</b>
⭐️ Nếu bạn thấy không chắc chắn điều gì, hãy chủ động tham khảo Admin trước khi vội vàng hành động.
⭐️ Admin sẽ không bao giờ nhắn tin riêng trước cho bạn.
⭐️ Nguồn lực của team là có hạn. Nếu bạn muốn được hỗ trợ tốt hơn, hãy ủng hộ team để được tham gia nhóm Premium 👉 nhắn tin cho @zayne120 hoặc<a href="https://t.me/CryptoVN101/1852">Làm theo hướng dẫn</a>."""

# ---------------------------------------------------------
# 3. CẤU HÌNH LỊCH ĐĂNG BÀI CHÍNH XÁC (SCHEDULES)
# ---------------------------------------------------------
# HƯỚNG DẪN ĐIỀN:
# Day: 0=Thứ 2, 1=Thứ 3, 2=Thứ 4, 3=Thứ 5, 4=Thứ 6, 5=Thứ 7, 6=Chủ Nhật
# Hour: Định dạng 24h (Ví dụ: 8 cho 8h sáng, 20 cho 8h tối)
# Minute: Phút (0 -> 59)
# Channels: Danh sách ID Kênh (Ví dụ "-10012345678" hoặc lấy DEFAULT_CHAT_ID từ .env)

# MẶC ĐỊNH SẼ ĐĂNG VÀO CHAT_ID BẠN ĐÃ CẤU HÌNH TRONG .ENV
# Có thể chèn cụ thể nhiều nhóm vào `.env`, ví dụ: TARGET_CHANNELS_TIN_1=-100123,-100456
TARGET_CHANNELS_TIN_1 = get_channels_from_env("TARGET_CHANNELS_TIN_1")
TARGET_CHANNELS_TIN_2 = get_channels_from_env("TARGET_CHANNELS_TIN_2")
TARGET_CHANNELS_TIN_3 = get_channels_from_env("TARGET_CHANNELS_TIN_3")

SCHEDULES = [
    # Cấu Hình Tin Nhắn 1 (Thứ Hai lúc 08:30)
    {"name": "Tin nhắn 1", "day": 5, "hour": 9, "minute": 00, "message": MESSAGE_1, "channels": TARGET_CHANNELS_TIN_1},
    
    # Cấu Hình Tin Nhắn 2 (Thứ Tư lúc 20:00)
    {"name": "Tin nhắn 2", "day": 5, "hour": 10, "minute": 00, "message": MESSAGE_2, "channels": TARGET_CHANNELS_TIN_2},
    
    # Cấu Hình Tin Nhắn 3 (Thứ Bảy lúc 09:00)
    {"name": "Tin nhắn 3", "day": 6, "hour": 9, "minute": 00, "message": MESSAGE_3, "channels": TARGET_CHANNELS_TIN_3},
]

# ---------------------------------------------------------
# THE SCHEDULING ENGINE
# ---------------------------------------------------------
# Tránh spam nhiều tin trong cùng 1 phút
_last_posted_timestamp = None

def send_telegram_message(chat_id: str, text: str):
    """Gửi tin nhắn qua Telegram API."""
    if not chat_id or chat_id == "-100xxxxx":
        print("⚠️ CẢNH BÁO: CHAT_ID chưa được định nghĩa chính xác. Bỏ qua.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": "HTML", # Bật HTML để chữ bọc Link
        "disable_web_page_preview": True # Tự động tắt link preview lớn để giữ gọn tin
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"  ✅ Đã gửi thành công vào channel {chat_id}")
            return True
        else:
            print(f"  ❌ Lỗi Telegram (Code {response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"  ⚠️ Exception khi gửi: {str(e)}")
        return False

def check_and_post():
    """Hàm kiểm tra thời gian hiện tại so với lịch biểu để quăng tin."""
    global _last_posted_timestamp
    
    # Ép sử dụng thời gian thực tế tại Việt Nam (kể cả khi rải lên Railway server)
    now = datetime.datetime.now(VN_TZ)
    current_day = now.weekday()   # 0-6
    current_hour = now.hour       # 0-23
    current_minute = now.minute   # 0-59
    
    # Mã nhận diện phút hiện tại (VD: Thứ 2 lúc 8:30 -> "0-8-30")
    current_time_signature = f"{current_day}-{current_hour}-{current_minute}"
    
    # Đã gửi trong phút này rồi thì thôi, chờ qua phút mới
    if _last_posted_timestamp == current_time_signature:
        return
        
    for job in SCHEDULES:
        if job["day"] == current_day and job["hour"] == current_hour and job["minute"] == current_minute:
            print(f"\n⏰ Phát bài: {job['name']} (Giờ VN: {now.strftime('%H:%M:%S')})")
            print(f"   Chuẩn bị đẩy tin tới {len(job['channels'])} channel(s): {job['channels']}")
            
            for channel in job["channels"]:
                send_telegram_message(channel, job["message"])
                
            # Đánh dấu phút này đã hoàn thành công việc
            _last_posted_timestamp = current_time_signature

def run_scheduler_sync():
    print("====================================================")
    print("🚀 BOT LÊN LỊCH TỰ ĐỘNG (WEEKLY ANNOUNCEMENT) ĐÃ CHẠY (SYNC MODE)")
    print("====================================================")
    print("📋 Lịch đã được nạp (Múi Giờ VN GMT+7):")
    days_vi = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    for j in SCHEDULES:
        print(f" - {j['name']}: {days_vi[j['day']]} lúc {j['hour']:02d}:{j['minute']:02d} -> Tới kênh: {j['channels']}")
    print("\nHệ thống sẽ quét mỗi 30 giây (Để treo ngầm nhé). Bấm Ctrl+C để tắt.")
    
    while True:
        try:
            check_and_post()
            time.sleep(30) # Vòng lặp nghỉ 30 giây để khỏi tốn CPU
        except KeyboardInterrupt:
            print("\n🛑 Đã nhận lệnh dừng (Ctrl+C). Thoát an toàn.")
            break
        except Exception as e:
            print(f"\n⚠️ Lỗi vòng lặp: {str(e)}")
            time.sleep(30)

async def run_scheduler_async():
    """Async wrapper for running the scheduler alongside other AI lanes in main.py"""
    import asyncio
    print("====================================================")
    print("🚀 BOT LÊN LỊCH TỰ ĐỘNG (WEEKLY ANNOUNCEMENT) ĐÃ CHẠY (ASYNC MODE)")
    print("====================================================")
    
    loop = asyncio.get_running_loop()
    
    while True:
        try:
            # Run the synchronous network requests in a separate thread to avoid blocking the Express listener
            await loop.run_in_executor(None, check_and_post)
            await asyncio.sleep(30)
        except Exception as e:
            print(f"\n⚠️ Lỗi vòng lặp Async Scheduler: {str(e)}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    run_scheduler_sync()
