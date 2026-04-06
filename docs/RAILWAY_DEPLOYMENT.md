# Hướng Dẫn Deploy Bot Lên Railway (V5.0)

Việc treo máy tính 24/7 ở nhà rất tốn điện và mạng không ổn định. Railway là dịch vụ máy chủ đám mây, tự động lấy code từ GitHub và chạy suốt ngày đêm.

---

## BƯỚC 1: LẤY "CHÌA KHÓA" TELEGRAM STRING SESSION (QUAN TRỌNG NHẤT)

Khi chạy trên Railway, Bot không có Terminal để bạn nhập mã Code 5 số mà Telegram gửi về điện thoại. Do đó, ta phải lấy sẵn một "String Session" trên máy tính nhà.

1. Bật thư mục gốc của Bot lên (trên máy tính của bạn).
2. Chắc chắn file `.env` đã có `TG_API_ID` và `TG_API_HASH`.
3. Mở Terminal, chạy lệnh sau:
   ```bash
   python generate_string_session.py
   ```
4. Nó sẽ hỏi bạn nhập số điện thoại (`+84...`) và mã Code từ App Telegram.
5. Sau khi thành công, nó sẽ in ra một đoạn chữ loằng ngoằng. Hãy **COPY đoạn mã đó**.
6. Mở file `.env` lên, tạo thêm một dòng mới:
   ```env
   TG_STRING_SESSION=dán_đoạn_mã_vào_đây
   ```

---

## BƯỚC 2: UP CODE LÊN GITHUB (PRIVATE REPO)

1. Đảm bảo file `.env` nằm trong `.gitignore` (để không bị lộ API KEY).
2. Push toàn bộ thư mục Bot lên một Repo **Private** trên GitHub.

---

## BƯỚC 3: KẾT NỐI VÀ DEPLOY TRÊN RAILWAY

1. Vào [Railway.app](https://railway.app), đăng nhập bằng tài khoản GitHub.
2. `New Project` → `Deploy from GitHub repo` → Chọn repo.
3. Nó sẽ deploy lần đầu (có thể báo lỗi, mặc kệ — chưa có Variables).

### Cài Volume Lưu Trữ Database:
Bot cần bộ nhớ lưu trữ DB SQLite.
1. Nhấp vào service → tab **Volumes**.
2. Tạo Volume mới, Mount Path gõ chính xác: `/app/data`
3. Ấn Save.

### Truyền Biến Môi Trường (Variables):
1. Chuyển sang tab **Variables**.
2. Bấm **"Raw Editor"**.
3. Copy toàn bộ nội dung file `.env` trên máy, dán vào.

**Biến MỚI cần thêm cho V5.0** (nếu chưa có trong `.env`):

```env
# === PER-PLATFORM TIMING (V5.0) ===
# Content Pipeline: quét RSS mỗi N phút
CONTENT_PIPELINE_INTERVAL=30

# Publisher: check timing mỗi N phút
PUBLISH_CHECK_INTERVAL=5

# Bài trong kho quá N giờ → expired
QUEUE_MAX_AGE_HOURS=6

# Telegram timing — Gap mode (check khoảng cách bài cuối trên channel)
TG_PUBLISH_MODE=gap
TG_MIN_GAP_HOURS=4
TG_GAP_CHANNEL_ID=@your_channel_username_here

# Twitter timing — Scheduled mode (đăng đúng giờ cố định)
TW_PUBLISH_MODE=scheduled
TW_SCHEDULE=07:00,11:00,15:00,18:00,21:00,00:00

# Facebook timing — Interval mode (cách đều N giờ)
FB_PUBLISH_MODE=interval
FB_INTERVAL_HOURS=6
```

4. Bấm `Update Variables` → Railway tự redeploy.

---

## BƯỚC 4: THEO DÕI LOG

### Cách đọc Log trên Railway:
1. Service → tab **Deployments** → **View Logs**.
2. **Các dòng quan trọng:**
   - `📡 [TIMING:TELEGRAM] Gap mode: 4.5h >= 4h → ĐẾN GIỜ ĐĂNG` — Timing checker
   - `📰 [PLATFORM PUBLISHER] TELEGRAM: Picked '...'` — Bot chọn bài từ kho
   - `✅ [PLATFORM PUBLISHER] TELEGRAM → POSTED` — Đăng thành công
   - `📭 [PLATFORM PUBLISHER] TELEGRAM: kho trống` — Chưa có bài mới trong kho
   - `📦 [QUEUE] Article '...' → kho` — Content Pipeline đã chuẩn bị bài sẵn
   - `📊 [ENTITY FATIGUE]` — Entity fatigue đang hoạt động
   - `🛡️ STARTUP GUARD: Skipping first cycle` — Bình thường, cycle đầu bỏ qua để tránh spam khi deploy

### Phân biệt Trùng Lặp (Idempotency):
- ✅ `POSTED`: Bài mới được đăng thành công.
- ⏭️ `SKIPPED (Duplicate)`: Bot nhận diện bài đã đăng → bỏ qua.

---

## BƯỚC 5: BẢO TRÌ VÀ CẬP NHẬT

- **Cập nhật code:** Push lên GitHub → Railway tự deploy bản mới trong 60 giây.
- **Hot-reload config:** Sửa Variables trên Railway → Bot nhận thay đổi ở cycle tiếp theo (không cần redeploy).
- **Bật/tắt luồng nhanh:** Sửa `RSS_ENABLED=False` hoặc `EXPRESS_ENABLED=False` trong Variables.

🎉 Tận hưởng cảm giác nhàn nhã nhìn Bot tự làm việc 24/7!
