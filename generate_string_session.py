from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import os
from dotenv import load_dotenv

load_dotenv()

api_id = os.environ.get("TG_API_ID")
api_hash = os.environ.get("TG_API_HASH")

if not api_id or not api_hash:
    print("❌ Lỗi: Bạn cần điền TG_API_ID và TG_API_HASH vào file .env trước khi chạy tool này.")
    exit(1)

print("\n--- CÔNG CỤ TẠO STRING SESSION CHO TELEGRAM ---")
print("Công cụ này giúp bạn đăng nhập Telegram 1 lần trên máy tính,")
print("và tạo ra một chuỗi mã hóa (String Session) để dán vào cấu hình của Server/Railway (biến TG_STRING_SESSION).")
print("--------------------------------------------------\n")

# Yêu cầu người dùng đăng nhập
with TelegramClient(StringSession(), int(api_id), api_hash) as client:
    session_string = client.session.save()
    print("\n✅ ĐĂNG NHẬP THÀNH CÔNG!")
    print("\n👇 HÃY COPY TOÀN BỘ CHUỖI VĂN BẢN BÊN DƯỚI VÀ DÁN VÀO FILE .ENV TẠO BIẾN MỚI MANG TÊN `TG_STRING_SESSION`:\n")
    print(session_string)
    print("\n(Chuỗi này giống như chìa khóa nhà của bạn, tuyệt đối không gửi cho người lạ!)")
