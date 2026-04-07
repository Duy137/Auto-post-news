# 🤖 Hướng Dẫn Sử Dụng Bot Điểm Báo AI (V5.1)

Chào mừng bạn! Đây là hệ thống **Biên tập viên AI** chuyên nghiệp, tự động săn tìm tin tức nóng hổi, dùng Trí Tuệ Nhân Tạo (Gemini) để tóm tắt thông minh và đăng bài tự động lên các mạng xã hội (Telegram, Twitter/X, Facebook) 24/7.

Hệ thống hoạt động với **3 vòng lặp song song + 1 scheduler lịch tuần**:
1. **Content Pipeline (Kho Bài):** Rà quét RSS → Chấm điểm → Tóm tắt → Lưu vào kho bài sẵn sàng.
2. **Platform Publisher (Đăng Bài):** Check timing từng nền tảng → Lấy bài tốt nhất từ kho → Đăng.
3. **Express Lane (Tin Cực Nhanh):** Nghe lỏng Telegram → Có tin Break → AI tóm tắt → Đăng ngay.
4. **Announcement Scheduler:** Đăng tin nhắn tự động theo lịch tuần (Quảng bá, nhắc nhở group).

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

Tạo file `.env` ngay trong thư mục Bot. Dưới đây là **toàn bộ** biến môi trường hệ thống hỗ trợ:

```env
# ═══════════════════════════════════════════════════
# 1. BỘ NÃO AI (Bắt buộc — chọn 1 trong 2)
# ═══════════════════════════════════════════════════
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...key_của_bạn

# Hoặc dùng OpenAI (bỏ comment nếu dùng):
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...

# ═══════════════════════════════════════════════════
# 2. TELEGRAM BOT — Đăng bài tự động (Bắt buộc)
# ═══════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN=8769006:AAH_bot_token_của_bạn
TELEGRAM_CHAT_ID=-100123456789

# (Tùy chọn) Chat ID riêng cho từng luồng:
# TELEGRAM_CHAT_ID_RSS=-100111111111
# TELEGRAM_CHAT_ID_EXPRESS=-100222222222

# ═══════════════════════════════════════════════════
# 3. CỔNG NGHE LỎNG TELEGRAM — Express Lane (Tùy chọn)
# ═══════════════════════════════════════════════════
# Lấy từ https://my.telegram.org
TG_API_ID=1234567
TG_API_HASH=abc123def456
TG_PHONE=+8498xxxxxxx
TG_SOURCE_CHANNEL=@KenhTinNhanhCuaBan

# ═══════════════════════════════════════════════════
# 4. TWITTER / X (Tùy chọn — chỉ cần nếu đăng Twitter)
# ═══════════════════════════════════════════════════
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# ═══════════════════════════════════════════════════
# 5. FACEBOOK FANPAGE (Tùy chọn — chỉ cần nếu đăng Facebook)
# ═══════════════════════════════════════════════════
FACEBOOK_PAGE_ACCESS_TOKEN=EAA...token_dài
FACEBOOK_PAGE_ID=123456789

# ═══════════════════════════════════════════════════
# 6. CÔNG TẮC BẬT/TẮT LUỒNG
# ═══════════════════════════════════════════════════
RSS_ENABLED=True
EXPRESS_ENABLED=True

# ═══════════════════════════════════════════════════
# 7. TIMING CỐT LÕI — Tốc độ quét & đăng bài
# ═══════════════════════════════════════════════════
# Content Pipeline quét RSS mỗi N phút (Default: 30)
CONTENT_PIPELINE_INTERVAL=30

# Publisher check timing mỗi N phút (Default: 5)
PUBLISH_CHECK_INTERVAL=5

# Bài trong kho quá N giờ → expired, bỏ (Default: 6)
QUEUE_MAX_AGE_HOURS=6

# ═══════════════════════════════════════════════════
# 8. PER-PLATFORM TIMING — Thời điểm đăng bài
# ═══════════════════════════════════════════════════

# --- TELEGRAM ---
# Mode: gap (check khoảng cách bài cuối), scheduled, interval
TG_PUBLISH_MODE=gap
TG_MIN_GAP_HOURS=4
TG_GAP_CHANNEL_ID=@your_channel_username
# Dùng cho mode scheduled:
# TG_SCHEDULE=07:00,11:00,15:00,18:00,21:00,00:00
# Dùng cho mode interval:
# TG_INTERVAL_HOURS=4

# --- TWITTER ---
TW_PUBLISH_MODE=scheduled
TW_SCHEDULE=07:00,11:00,15:00,18:00,21:00,00:00
# TW_INTERVAL_HOURS=6

# --- FACEBOOK ---
FB_PUBLISH_MODE=scheduled
FB_SCHEDULE=07:00,12:00,18:00,22:00
# FB_INTERVAL_HOURS=6
```

> **🔥 Hot-Reload:** Mọi biến trên được reload tự động mỗi vòng lặp mà **không cần restart** bot. Trên Railway, chỉ cần thay đổi env var → bot tự áp dụng trong 5 phút.

---

## 🚀 PHẦN 3: THIẾT LẬP TỪNG NỀN TẢNG

### 3.1 Telegram (Bắt buộc — nền tảng chính)

**Bước 1:** Tạo bot tại [@BotFather](https://t.me/BotFather), lấy `TELEGRAM_BOT_TOKEN`.

**Bước 2:** Tạo channel/group, thêm bot làm Admin, lấy `TELEGRAM_CHAT_ID`.
> Mẹo: Forward 1 tin nhắn từ channel vào [@userinfobot](https://t.me/userinfobot) để lấy ID channel.

**Bước 3:** Chọn chế độ timing:

| Mode | Cách hoạt động | Env vars cần thiết |
|:---|:---|:---|
| `gap` ⭐ | Check bài cuối trên channel, đợi ≥ N giờ mới đăng | `TG_PUBLISH_MODE=gap`, `TG_MIN_GAP_HOURS=4`, `TG_GAP_CHANNEL_ID` |
| `scheduled` | Đăng đúng khung giờ cố định (±5 phút) | `TG_PUBLISH_MODE=scheduled`, `TG_SCHEDULE=07:00,11:00,...` |
| `interval` | Cách đều N giờ kể từ lần đăng trước (DB nội bộ) | `TG_PUBLISH_MODE=interval`, `TG_INTERVAL_HOURS=4` |

> **Khuyên dùng `gap`** cho Telegram — vì nó check trực tiếp bài cuối trên channel qua Telethon API, nên dù bạn đăng thủ công hay bot khác đăng, nó vẫn biết và đợi đúng khoảng cách.

**Bước 4 (Cho mode gap):** Thiết lập Telethon session:
- Set `TG_API_ID`, `TG_API_HASH`, `TG_PHONE` trong `.env`
- Set `TG_GAP_CHANNEL_ID` = username channel (`@channelname`) hoặc numeric ID (`-100xxx`)
- Lần chạy đầu tiên, Telethon sẽ yêu cầu nhập mã OTP qua Telegram → nhập 1 lần, sau đó tự nhớ session.

---

### 3.2 Facebook Fanpage

**Bước 1:** Tạo Facebook App tại [developers.facebook.com](https://developers.facebook.com).

**Bước 2:** Lấy Page Access Token (loại long-lived):
- Vào **Graph API Explorer** → Chọn Page → Generate Token
- Cần quyền: `pages_manage_posts`, `pages_read_engagement`
- Chuyển thành **long-lived token** (60 ngày) hoặc dùng System User token (không hết hạn)

**Bước 3:** Set env vars:
```env
FACEBOOK_PAGE_ACCESS_TOKEN=EAA...rất_dài
FACEBOOK_PAGE_ID=123456789
FB_PUBLISH_MODE=scheduled
FB_SCHEDULE=07:00,12:00,18:00,22:00
```

**Bước 4:** Bật Facebook trong `config.py`:
```python
# config.py dòng 63-66
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS": ["telegram", "facebook"]   # ← thêm "facebook"
}
```

> **Lưu ý:** Facebook Page Access Token có thời hạn. Token ngắn hạn = 1 giờ, long-lived = 60 ngày. Khuyên dùng **System User Token** (permanent) cho production.

---

### 3.3 Twitter / X

**Bước 1:** Đăng ký Developer Account tại [developer.twitter.com](https://developer.twitter.com).

**Bước 2:** Tạo Project + App → Lấy 4 keys:
```env
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_SECRET=...
```

**Bước 3:** Bật Twitter trong `config.py`:
```python
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS": ["telegram", "twitter"]   # ← thêm "twitter"
}
```

---

## ⚡ PHẦN 4: BẬT NGUỒN VÀ LÁI BOT

### Khởi chạy
```bash
python main.py
```

**Thế là xong!** Hệ thống tự chạy 4 task song song:
- **Content Pipeline** — quét RSS mỗi 30 phút, chuẩn bị bài vào kho
- **Platform Publisher** — mỗi 5 phút check xem platform nào đến giờ đăng
- **Express Listener** — luôn lắng nghe Telegram, có tin break → đăng ngay
- **Announcement Scheduler** — đăng tin nhắn quảng bá theo lịch tuần

### Bật / Tắt nền tảng đăng bài

Mở `config.py`, tìm `PLATFORM_MAPPING`:

```python
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],              # Express chỉ đăng Telegram
    "RSS": ["telegram", "facebook"]       # RSS đăng cả Telegram + Facebook
}
```

Bỏ platform ra khỏi list = tắt đăng trên platform đó. Không cần bỏ env vars.

### Bật / Tắt công tắc luồng RSS / Express

Trong `.env`:
```env
RSS_ENABLED=True       # True = bật luồng RSS
EXPRESS_ENABLED=True   # True = bật luồng Express (nghe lỏng Telegram)
```

Hoặc hot-reload từ Railway dashboard mà không cần redeploy.

### Chế độ nháp "Bắn Chỉ Thiên"

Mở `config.py`, tìm `TWITTER_CONFIG`:
```python
"dry_run": True   # True = chỉ in log, KHÔNG đăng thật lên bất kỳ platform nào
```

> Dry_run áp dụng cho **TẤT CẢ** platform (Telegram, Twitter, Facebook), không riêng Twitter.

---

## ⚙️ PHẦN 5: TÙY CHỈNH BOT

### 1. Chế Độ Timing — Giải Thích Chi Tiết

```
┌─────────────────────────────────────────────────────────────────┐
│                    PUBLISH CHECK LOOP                            │
│                    (Mỗi 5 phút)                                 │
│                                                                 │
│  for platform in PLATFORM_MAPPING["RSS"]:                       │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │  should_publish_now(platform)                           │  │
│    │                                                         │  │
│    │  ┌── gap mode ──────────────────────────────────────┐   │  │
│    │  │  Lấy thời gian bài cuối trên channel             │   │  │
│    │  │  (Telethon API cho TG, DB cho platform khác)      │   │  │
│    │  │  → Nếu gap ≥ min_gap_hours → ĐẾN GIỜ            │   │  │
│    │  └──────────────────────────────────────────────────┘   │  │
│    │  ┌── scheduled mode ────────────────────────────────┐   │  │
│    │  │  Check nếu "bây giờ" nằm trong ±5 phút          │   │  │
│    │  │  của 1 slot trong schedule list                    │   │  │
│    │  │  → Nếu đúng slot + chưa đăng slot này → ĐẾN GIỜ │   │  │
│    │  └──────────────────────────────────────────────────┘   │  │
│    │  ┌── interval mode ─────────────────────────────────┐   │  │
│    │  │  Check DB: lần đăng cuối platform này             │   │  │
│    │  │  → Nếu hours_since ≥ interval_hours → ĐẾN GIỜ    │   │  │
│    │  └──────────────────────────────────────────────────┘   │  │
│    │                                                         │  │
│    │  Nếu ĐẾN GIỜ → pick_best_from_queue(platform) → Đăng  │  │
│    └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Keyword Scoring (Mục `SCORING_WEIGHTS` trong `config.py`)
- **`keyword_categories`**: Các rổ từ khóa quyết định điểm bài viết
- **`keyword_caps`**: Điểm trần mỗi rổ (ví dụ: `macro_politics: 5.0`, `negative_event: 8.0`)
- **`major_tokens` / `major_exchanges` / `macro_entities`**: Entity lists — bài có entity ở đây được cộng điểm thưởng
- **`min_publish_score = 5.0`**: Ngưỡng tối thiểu để bài được đăng
- **`noise_tokens`**: Bitcoin/ETH bị giảm 50% điểm dương (tránh spam)

> Xem chi tiết tại `docs/ranking_engine_documentation.md`.

### 3. Entity Fatigue (V5.1)
Bot tự động phạt bài khi cùng 1 chủ đề/entity được đăng quá nhiều trong 24h:
- Lần 2: ×0.8 điểm
- Lần 3: ×0.6 điểm
- Lần 5+: ×0.0 (triệt tiêu hoàn toàn)

Cơ chế này dùng `extract_fingerprints()` để detect MỌI entity tự động (proper nouns, $TOKEN, ALL CAPS), không cần config thủ công.

> **Lưu ý:** Entity Fatigue chỉ đếm bài từ luồng RSS. Luồng Express độc lập, không ảnh hưởng lẫn nhau.

### 4. Prompt AI (Mục `PROMPT_TEMPLATES` trong `config.py`)
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

### 6. Announcement Scheduler (Lịch đăng bài tự động hàng tuần)
File `auto_announcement.py`:
- Cấu hình tin nhắn trong `MESSAGE_1`, `MESSAGE_2`...
- Cấu hình lịch đăng trong `SCHEDULES`:
```python
SCHEDULES = [
    {"name": "Tin 1", "day": 5, "hour": 9, "minute": 0, "message": MESSAGE_1, "channels": TARGET_CHANNELS},
    # day: 0=Thứ 2, 1=Thứ 3, ..., 5=Thứ 7, 6=Chủ Nhật
]
```
- Hỗ trợ gửi ảnh: thêm `"image": "photos/file.jpg"` hoặc URL
- Tự động retry + TTL 2 giờ + atomic locking

---

## 📋 PHẦN 6: CẤU TRÚC THƯ MỤC

```
Auto post news/
├── main.py                    ← Điểm khởi chạy chính (4 task song song)
├── config.py                  ← Toàn bộ cấu hình (SCORING, TIMING, PLATFORMS)
├── auto_announcement.py       ← Scheduler lịch đăng bài tuần
├── models.py                  ← TypedDict definitions
├── .env                       ← API Keys + biến điều khiển (BẢO MẬT — KHÔNG commit)
├── requirements.txt           ← Thư viện cần cài
├── Procfile                   ← Railway worker config
│
├── modules/
│   ├── state_manager.py       ← Database SQLite (articles, queue, publish log...)
│   ├── __init__.py            ← Package marker
│   │
│   ├── pipeline/              ← RSS Content Pipeline
│   │   ├── collector.py       ← Phase 1: Thu thập RSS
│   │   ├── deduplicator.py    ← Phase 2: Lọc trùng (Jaccard + entity)
│   │   ├── rank.py            ← Phase 3: Chấm điểm (keyword + entity + decay)
│   │   ├── selector.py        ← Phase 4: Chọn bài tốt nhất (diversity check)
│   │   └── summarize.py       ← Phase 5: AI tóm tắt (Gemini/OpenAI)
│   │
│   ├── express/               ← Express Lane (Tin Nhanh)
│   │   ├── listener.py        ← Telethon listener — nghe tin từ channel nguồn
│   │   ├── filter.py          ← Lọc tin Express (keyword, score threshold)
│   │   └── fingerprint.py     ← Entity extraction — dùng chung cho cả RSS
│   │
│   └── publishing/            ← Đăng bài đa nền tảng
│       ├── publisher.py       ← Telegram/Twitter/Facebook API integration
│       ├── timing.py          ← Per-platform timing logic (gap/scheduled/interval)
│       └── telethon_client.py ← Singleton Telethon client (Express + Gap check)
│
├── data/                      ← Database file (auto-generated, mount volume trên Railway)
│   └── article_state.db
│
├── photos/                    ← Ảnh cho Announcement Scheduler
│
└── docs/                      ← Tài liệu chi tiết
    ├── PROJECT_SNAPSHOT.md
    ├── ranking_engine_documentation.md
    ├── deduplication_documentation.md
    ├── RAILWAY_DEPLOYMENT.md
    └── removed_features_consideration.md
```

---

## 🔧 PHẦN 7: XỬ LÝ SỰ CỐ

| Triệu chứng | Nguyên nhân | Giải pháp |
|:---|:---|:---|
| Bot không đăng bài | Kho trống (không có bài score ≥ 5.0) | Check log `[RANK DEBUG]`, xem bài báo nào bị score thấp |
| Bot đăng liên tục | `TG_MIN_GAP_HOURS` quá nhỏ | Tăng lên 4-6 giờ |
| Express không hoạt động | Telethon session hết hạn | Xóa file `*.session` trong thư mục gốc, chạy lại |
| Facebook lỗi 403 | Token hết hạn hoặc thiếu quyền | Tạo lại token với quyền `pages_manage_posts` |
| Tin bị lặp topic | Entity Fatigue chưa tác dụng | Kiểm tra `get_posted_titles_24h()` trả về đúng không |
| Log spam `[SCHEDULER]` | Bug cũ đã fix — nếu vẫn xảy ra | Pull code mới nhất |

---

Chúc bạn sở hữu cỗ máy tin tức AI tự động bá đạo nhất! 🚀
