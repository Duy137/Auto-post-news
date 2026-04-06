# 🤖 Hướng Dẫn Sử Dụng Bot Điểm Báo AI (V5.1)

Chào mừng bạn! Đây là hệ thống **Biên tập viên AI** chuyên nghiệp, tự động săn tìm tin tức nóng hổi, dùng Trí Tuệ Nhân Tạo (Gemini) để tóm tắt thông minh và đăng bài tự động lên các mạng xã hội (Telegram, Twitter/X, Facebook) 24/7.

Hệ thống hoạt động với **3 vòng lặp song song**:
1. **Content Pipeline (Kho Bài):** Rà quét RSS → Chấm điểm → Tóm tắt → Lưu vào kho bài sẵn sàng.
2. **Platform Publisher (Đăng Bài):** Check timing từng nền tảng → Lấy bài tốt nhất từ kho → Đăng.
3. **Express Lane (Tin Cực Nhanh):** Nghe lỏng Telegram → Có tin Break → AI tóm tắt → Đăng ngay.

---

## 🛠️ PHẦN 1: CÁC BƯỚC CÀI ĐẶT LẦN ĐẦU

### Bước 1: Cài đặt phần mềm nền tảng
1. Tải và cài đặt **Python** (Bản 3.10 trở lên) tại `python.org`.
   > **Lưu ý QUAN TRỌNG:** Khi cài đặt, nhớ tích ✔️ `"Add Python to PATH"`.
2. Tải mã nguồn Bot về máy, giải nén vào thư mục (Ví dụ: `D:\Auto post news`).

### Bước 2: Cài đồ nghề cho Bot
```bash
cd "D:\Auto post news"
pip install -r requirements.txt
```

---

## 🔑 PHẦN 2: CẤU HÌNH BẢO MẬT (`.env`)

Tạo file `.env` ngay trong thư mục Bot:

```env
# ----- 1. BỘ NÃO AI -----
LLM_PROVIDER=gemini
GEMINI_API_KEY=điền_key_gemini_vào_đây

# ----- 2. NỀN TẢNG ĐĂNG BÀI -----
# Telegram Bot
TELEGRAM_BOT_TOKEN=8769006...
TELEGRAM_CHAT_ID=-100123...

# Twitter / X
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# Facebook Fanpage
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=

# ----- 3. CỔNG NGHE LỎNG TELEGRAM (Express Lane) -----
TG_API_ID=1234567
TG_API_HASH=điền_chuỗi_hash
TG_PHONE=+8498xxxxxxx
TG_SOURCE_CHANNEL=@KenhTinNhanhCuaBan

# ----- 4. CÔNG TẮC CHÍNH -----
RSS_ENABLED=True
EXPRESS_ENABLED=True

# ----- 5. PER-PLATFORM TIMING (V5.0) -----
# Content Pipeline quét RSS mỗi N phút
CONTENT_PIPELINE_INTERVAL=30

# Publisher check timing mỗi N phút
PUBLISH_CHECK_INTERVAL=5

# Bài quá N giờ → expired, không đăng
QUEUE_MAX_AGE_HOURS=6

# Telegram: check khoảng cách bài cuối ≥ 4 giờ mới đăng tiếp
TG_PUBLISH_MODE=gap
TG_MIN_GAP_HOURS=4
TG_GAP_CHANNEL_ID=@your_channel

# Twitter: đăng theo khung giờ cố định
TW_PUBLISH_MODE=scheduled
TW_SCHEDULE=07:00,11:00,15:00,18:00,21:00,00:00

# Facebook: cách đều mỗi 6 giờ
FB_PUBLISH_MODE=interval
FB_INTERVAL_HOURS=6
```

---

## 🚀 PHẦN 3: BẬT NGUỒN VÀ LÁI BOT

### Bật / Tắt nền tảng đăng bài
Mở `config.py`, tìm `PLATFORM_MAPPING`:

```python
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS": ["telegram"]     # Thêm "twitter", "facebook" nếu cần
}
```

### Chế độ nháp "Bắn Chỉ Thiên"
Mở `config.py`, tìm `TWITTER_CONFIG`:
```python
"dry_run": True   # True = chỉ in ra, không đăng lên mạng
```

### Khởi chạy
```bash
python main.py
```

**Thế là xong!** Hệ thống tự chạy 3 vòng lặp song song:
- **Content Pipeline** — quét RSS mỗi 30 phút, chuẩn bị bài vào kho
- **Platform Publisher** — mỗi 5 phút check xem platform nào đến giờ đăng
- **Express Listener** — luôn lắng nghe Telegram, có tin break → đăng ngay

🔥 **Hot-Reload:** Sửa `.env` → Bot tự nhận diện mà không cần restart!

---

## ⚙️ PHẦN 4: TÙY CHỈNH BOT

### 1. Chế Độ Timing Từng Platform (V5.0)

| Mode | Mô tả | Dùng khi |
|:---|:---|:---|
| `gap` | Check bài cuối trên channel, đợi đủ N giờ mới đăng tiếp | Telegram — tránh spam channel |
| `scheduled` | Đăng đúng khung giờ cố định (±5 phút) | Twitter/X — nội dung ổn định |
| `interval` | Cách đều N giờ kể từ lần đăng trước | Facebook — đều đặn |

Điều chỉnh trong `.env` hoặc trực tiếp default trong `config.py` (dòng 77-97).

### 2. Keyword Scoring (Mục `SCORING_WEIGHTS` trong `config.py`)
- **`keyword_categories`**: Các rổ từ khóa quyết định điểm bài viết
- **`major_tokens` / `major_exchanges` / `macro_entities`**: Entity lists — bài có entity ở đây được cộng điểm thưởng
- **`min_publish_score = 5.0`**: Ngưỡng tối thiểu để bài được đăng

### 3. Entity Fatigue (V5.1)
Bot tự động phạt bài khi cùng 1 chủ đề/entity được đăng quá nhiều trong 24h:
- Lần 2: ×0.8 điểm
- Lần 3: ×0.6 điểm
- Lần 5+: ×0.0 (bỏ hẳn)

Cơ chế này dùng `extract_fingerprints()` để detect MỌI entity tự động, không cần config thủ công.

### 4. Prompt AI (Mục `PROMPT_TEMPLATES`)
Tùy chỉnh văn phong riêng cho mỗi luồng:
- **RSS**: Phong cách nghiêm túc, chuyên nghiệp
- **EXPRESS**: Phong cách khẩn cấp, nhanh gọn

### 5. Nạp Thêm Nguồn Báo (Mục `RSS_SOURCES`)
```python
{
    "id": "source_id",
    "name": "Tên Nguồn",
    "url": "https://example.com/rss",
    "credibility_score": 1.1,     # 1.0 = bình thường, >1.0 = tin cậy hơn
    "latency_advantage_score": 1.0
}
```

---

## 📋 PHẦN 5: CẤU TRÚC THƯ MỤC

```
Auto post news/
├── main.py                    ← Điểm khởi chạy chính
├── config.py                  ← Toàn bộ cấu hình
├── .env                       ← API Keys + biến điều khiển
├── requirements.txt           ← Thư viện cần cài
├── Procfile                   ← Railway worker config
├── modules/
│   ├── state_manager.py       ← Database SQLite
│   ├── pipeline/              ← RSS: collector → dedup → rank → selector → summarize
│   ├── express/               ← Express: listener → filter → fingerprint
│   └── publishing/            ← Publisher: publisher + timing + telethon_client
├── data/                      ← Database file (auto-generated)
└── docs/                      ← Tài liệu
```

Chúc bạn sở hữu cỗ máy tin tức AI tự động bá đạo nhất! 🚀
