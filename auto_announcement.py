import os
import time
import datetime
import requests
import json
import sqlite3
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
⭐️ Nguồn lực của team là có hạn. Nếu bạn muốn được hỗ trợ tốt hơn, hãy ủng hộ team để được tham gia nhóm Premium 👉 nhắn tin cho @zayne120 hoặc<a href="https://t.me/CryptoVN101/1852"> làm theo hướng dẫn</a>."""

MESSAGE_4 = """🚨 NHẮC NHỞ NHẸ CUỐI TUẦN – DUY TRÌ QUYỀN LỢI

Chào anh em 👋
Team gửi một nhắc nhở nhỏ để mọi người nắm rõ cách group vận hành 👇

💡 Group hoạt động theo tinh thần win-win:
🫡 Team luôn cố gắng nâng cấp sản phẩm, giúp anh em có lợi thế trên thị trường — đó là cam kết và tâm huyết của team.
🤝 Đồng thời, sự tham gia giao dịch của anh em là yếu tố giúp team duy trì và phát triển giá trị lâu dài.

📊 Điều kiện duy trì Premium Hub:
1️⃣ Volume tối thiểu 3000 USD / tháng trên các sàn đối tác của CryptoVN 101
2️⃣ Nếu không phát sinh giao dịch trong 3 tháng liên tiếp, team sẽ tạm thời remove khỏi group
3️⃣ Việc rà soát sẽ được thực hiện định kỳ mỗi tháng

🙏 Mong ae hiểu và góp sức cùng team gây dựng một cộng đồng đầu tư tử tế, chất lượng.

💬 Nếu cần hỗ trợ hoặc góp ý, anh em cứ phản hồi hoặc inbox admin — team luôn sẵn sàng lắng nghe.

🔥  Cảm ơn anh em đã luôn đồng hành và ủng hộ CryptoVN 101!"""

# ---------------------------------------------------------
# 3. CẤU HÌNH LỊCH ĐĂNG BÀI CHÍNH XÁC (SCHEDULES)
# ---------------------------------------------------------
# HƯỚNG DẪN ĐIỀN:
# Day: 0=Thứ 2, 1=Thứ 3, 2=Thứ 4, 3=Thứ 5, 4=Thứ 6, 5=Thứ 7, 6=Chủ Nhật
# Hour: Định dạng 24h (Ví dụ: 8 cho 8h sáng, 20 cho 8h tối)
# Minute: Phút (0 -> 59)
# Channels: Danh sách ID Kênh (Ví dụ "-10012345678" hoặc lấy DEFAULT_CHAT_ID từ .env)
# Image (optional): Đường dẫn file ảnh local hoặc URL. Nếu có, tin nhắn sẽ gửi kèm ảnh.

# MẶC ĐỊNH SẼ ĐĂNG VÀO CHAT_ID BẠN ĐÃ CẤU HÌNH TRONG .ENV
# Có thể chèn cụ thể nhiều nhóm vào `.env`, ví dụ: TARGET_CHANNELS_TIN_1=-100123,-100456
TARGET_CHANNELS_TIN_1 = get_channels_from_env("TARGET_CHANNELS_TIN_1")
TARGET_CHANNELS_TIN_2 = get_channels_from_env("TARGET_CHANNELS_TIN_2")
TARGET_CHANNELS_TIN_3 = get_channels_from_env("TARGET_CHANNELS_TIN_3")
TARGET_CHANNELS_TIN_4 = get_channels_from_env("TARGET_CHANNELS_TIN_4")

SCHEDULES = [
    # Cấu Hình Tin Nhắn 1 (Thứ Bảy lúc 09:00)
    {"name": "Tin nhắn 1", "day": 5, "hour": 9, "minute": 00, "message": MESSAGE_1, "channels": TARGET_CHANNELS_TIN_1},
    
    # Cấu Hình Tin Nhắn 2 (Thứ Bảy lúc 10:00)
    {"name": "Tin nhắn 2", "day": 5, "hour": 10, "minute": 00, "message": MESSAGE_2, "channels": TARGET_CHANNELS_TIN_2},
    
    # Cấu Hình Tin Nhắn 3 (Chủ Nhật lúc 09:00)
    {"name": "Tin nhắn 3", "day": 6, "hour": 9, "minute": 00, "message": MESSAGE_3, "channels": TARGET_CHANNELS_TIN_3},
    
    # Cấu Hình Tin Nhắn 4 (Chủ Nhật lúc 10:00) — Nhắc nhở cuối tuần, có thể kèm ảnh
    # Để thêm ảnh: thêm key "image": "assets/reminder.png" hoặc URL ảnh
    {"name": "Tin nhắn 4", "day": 6, "hour": 9, "minute": 00, "message": MESSAGE_4, "channels": TARGET_CHANNELS_TIN_4, "image": "photos/nhac-nho-giao-dich-cryptovn101.jpg"},
]

# ---------------------------------------------------------
# 4. DATA MODEL & SCHEDULE MATERIALIZATION
# ---------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "announcements.db")

def init_db():
    """Khởi tạo cấu trúc Database cho Lịch tự động."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS announcement_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            message_text TEXT NOT NULL,
            target_channels TEXT NOT NULL,
            scheduled_time DATETIME NOT NULL,
            status TEXT DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0,
            next_retry_at DATETIME,
            image_path TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_schedule 
        ON announcement_executions(job_name, scheduled_time)
    ''')
    # Migration: thêm cột image_path nếu DB cũ chưa có
    try:
        cursor.execute("ALTER TABLE announcement_executions ADD COLUMN image_path TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Cột đã tồn tại
    conn.commit()
    conn.close()

def materialize_schedules():
    """Dự phóng lịch đăng bài từ SCHEDULES vào Database cho 7 ngày tới."""
    now = datetime.datetime.now(VN_TZ)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted_count = 0
    updated_count = 0
    # Quét từ hôm nay đến 6 ngày tới (đúng 1 tuần = 7 ngày)
    for d_offset in range(7):
        target_date = now + datetime.timedelta(days=d_offset)
        target_weekday = target_date.weekday()
        
        for job in SCHEDULES:
            if job["day"] == target_weekday:
                # Lắp đúng giờ phút
                job_time = target_date.replace(hour=job["hour"], minute=job["minute"], second=0, microsecond=0)
                
                # Bỏ qua nếu lịch này mốc sinh ra đã ở trong quá khứ so với thời điểm khởi động
                if job_time < now:
                    continue
                    
                channels_json = json.dumps(job["channels"])
                image_path = job.get("image", "")  # Optional: đường dẫn ảnh
                # Định dạng ISO cục bộ (VN_TZ) để so sánh chuỗi
                scheduled_str = job_time.strftime('%Y-%m-%d %H:%M:%S')
                
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO announcement_executions 
                        (job_name, message_text, target_channels, scheduled_time, status, image_path)
                        VALUES (?, ?, ?, ?, 'PENDING', ?)
                    ''', (job["name"], job["message"], channels_json, scheduled_str, image_path))
                    if cursor.rowcount > 0:
                        inserted_count += 1
                    else:
                        # Cập nhật config mới nhất cho job PENDING (chống stale data khi env var thay đổi)
                        cursor.execute('''
                            UPDATE announcement_executions 
                            SET target_channels = ?, image_path = ?, message_text = ?
                            WHERE job_name = ? AND scheduled_time = ? AND status = 'PENDING'
                        ''', (channels_json, image_path, job["message"], job["name"], scheduled_str))
                        if cursor.rowcount > 0:
                            updated_count += 1
                except sqlite3.Error as e:
                    print(f"⚠️ Lỗi Materialize DB: {e}")
                    
    conn.commit()
    conn.close()
    if inserted_count > 0:
        print(f"📅 [SCHEDULER] Đã sinh {inserted_count} lịch mới cho 7 ngày tới.")

# ---------------------------------------------------------
# THE SCHEDULING ENGINE
# ---------------------------------------------------------

def send_telegram_message(chat_id: str, text: str):
    """Gửi tin nhắn text qua Telegram API."""
    if not chat_id or chat_id == "-100xxxxx":
        print("⚠️ CẢNH BÁO: CHAT_ID chưa được định nghĩa chính xác. Bỏ qua.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
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

def send_telegram_photo(chat_id: str, image_path: str, caption: str = ""):
    """Gửi ảnh kèm caption qua Telegram API.
    image_path có thể là:
      - Đường dẫn file local (ví dụ: 'assets/reminder.png')
      - URL ảnh trên internet (ví dụ: 'https://example.com/image.jpg')
    """
    if not chat_id or chat_id == "-100xxxxx":
        print("⚠️ CẢNH BÁO: CHAT_ID chưa được định nghĩa chính xác. Bỏ qua.")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    try:
        # Nếu là URL → gửi qua field 'photo' trong JSON
        if image_path.startswith("http://") or image_path.startswith("https://"):
            payload = {
                "chat_id": str(chat_id).strip(),
                "photo": image_path,
                "caption": caption,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=30)
        else:
            # File local → gửi qua multipart upload
            abs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), image_path)
            if not os.path.exists(abs_path):
                print(f"  ❌ Không tìm thấy file ảnh: {abs_path}")
                return False
            
            with open(abs_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {
                    "chat_id": str(chat_id).strip(),
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                response = requests.post(url, data=data, files=files, timeout=30)
        
        if response.status_code == 200:
            print(f"  ✅ Đã gửi ảnh + caption thành công vào channel {chat_id}")
            return True
        else:
            print(f"  ❌ Lỗi Telegram sendPhoto (Code {response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"  ⚠️ Exception khi gửi ảnh: {str(e)}")
        return False

MAX_RETRIES = 3
# Lịch trình Backoff theo phút (Lần 1: đợi 5p, Lần 2: đợi 15p, Lần 3: đợi 60p)
RETRY_BACKOFF_MINS = {1: 5, 2: 15, 3: 60} 

def check_and_post():
    """Hệ thống quét lịch và bắn Telegram (đủ TTL, Atomic Locking, Retries)."""
    # 1. Đảm bảo DB và liệu lịch dự phóng cho 7 ngày tới luôn sẵn sàng
    init_db()
    materialize_schedules()
    
    now = datetime.datetime.now(VN_TZ)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 2. TTL Cleanup (Dọn rác các job quá 2 tiếng chưa chạy được để tránh gửi tin nhắn lạc hậu do server down)
    expiration_limit = (now - datetime.timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        UPDATE announcement_executions 
        SET status = 'EXPIRED' 
        WHERE status = 'PENDING' AND scheduled_time < ?
    ''', (expiration_limit,))
    if cursor.rowcount > 0:
        print(f"🗑️ [SCHEDULER] Đã hủy (EXPIRED) {cursor.rowcount} job quá hạn 2 tiếng.")
        conn.commit()
        
    # 2.5 Routine Maintenance (Xóa vĩnh viễn dữ liệu cũ hơn 30 ngày để chống phình DB)
    prune_limit = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        DELETE FROM announcement_executions 
        WHERE scheduled_time < ?
    ''', (prune_limit,))
    if cursor.rowcount > 0:
        print(f"🧹 [SCHEDULER] Đã xóa vĩnh viễn {cursor.rowcount} lịch sử post cũ hơn 30 ngày để tối ưu DB.")
        conn.commit()
        
    # 3. Lấy Top 10 job tới giờ chạy (Initial hoặc Retry) tránh starvation
    cursor.execute('''
        SELECT * FROM announcement_executions 
        WHERE status = 'PENDING' 
          AND (
             (next_retry_at IS NULL AND scheduled_time <= ?)
             OR
             (next_retry_at IS NOT NULL AND next_retry_at <= ?)
          )
        ORDER BY scheduled_time ASC LIMIT 10
    ''', (now_str, now_str))
    pending_jobs = cursor.fetchall()
    
    for job in pending_jobs:
        job_id = job["id"]
        
        # 4. Atomic Lock (Khóa tiến trình chống chạy trùng lặp)
        cursor.execute('''
            UPDATE announcement_executions 
            SET status = 'PROCESSING' 
            WHERE id = ? AND status = 'PENDING'
        ''', (job_id,))
        if cursor.rowcount == 0:
            continue # Job đã bị instance khác chiếm quyền chạy, bỏ qua
        conn.commit() # Chốt lock
        
        # 5. Thực thi (Execution)
        print(f"\n⏰ Phát bài: {job['job_name']} (Scheduled: {job['scheduled_time']} | Try: {job['retry_count'] + 1})")
        
        channels = json.loads(job["target_channels"])
        all_success = True
        
        image = job["image_path"] if job["image_path"] else ""
        
        for channel in channels:
            if image:
                # Gửi ảnh kèm caption (text là caption của ảnh)
                success = send_telegram_photo(channel, image, job["message_text"])
            else:
                success = send_telegram_message(channel, job["message_text"])
            if not success:
                all_success = False
                
        # 6. Post-Execution (Cập nhật kết quả)
        if all_success:
            cursor.execute("UPDATE announcement_executions SET status = 'SUCCESS' WHERE id = ?", (job_id,))
        else:
            new_retry_count = job["retry_count"] + 1
            if new_retry_count > MAX_RETRIES:
                print(f"  ❌ Hết số lần thử lại (Max {MAX_RETRIES}). Job thất bại vĩnh viễn.")
                cursor.execute("UPDATE announcement_executions SET status = 'FAILED', retry_count = ? WHERE id = ?", (new_retry_count, job_id))
            else:
                backoff_mins = RETRY_BACKOFF_MINS.get(new_retry_count, 60)
                next_retry = now + datetime.timedelta(minutes=backoff_mins)
                next_retry_str = next_retry.strftime('%Y-%m-%d %H:%M:%S')
                print(f"  ⏳ Lỗi gửi tin. Sẽ thử lại lần {new_retry_count} vào {next_retry_str}")
                
                cursor.execute('''
                    UPDATE announcement_executions 
                    SET status = 'PENDING', retry_count = ?, next_retry_at = ?
                    WHERE id = ?
                ''', (new_retry_count, next_retry_str, job_id))
                
        conn.commit()
    conn.close()

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
