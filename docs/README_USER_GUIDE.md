# 🤖 Hướng Dẫn Sử Dụng Bot Điểm Báo AI Đa Luồng (Dual-Lane)

Chào mừng bạn! Đây là hệ thống **Biên tập viên AI** chuyên nghiệp, tự động săn tìm tin tức nóng hổi, dùng Trí Tuệ Nhân Tạo (Gemini/OpenAI) để tóm tắt thông minh và đăng bài tự động lên các mạng xã hội (Twitter/X, Telegram, Facebook) của bạn 24/7.

Hệ thống hoạt động với sức mạnh **"Đa Luồng" (Dual-Lane)**:
1. **Luồng RSS (Báo Phân Tích):** Rà quét các trang báo định kỳ (vd: mỗi 15 phút), tự chấm điểm độ nóng của tin, gạn lọc tin trùng, và chọn ra tin hay nhất để tóm tắt và đăng.
2. **Luồng Express (Tin Cực Nhanh):** Cắm trực tiếp vào ứng dụng Telegram của bạn để nghe lóng một kênh tin tức khẩn cấp. Vừa có tin "Break" là AI lập tức xào nấu và phóng lên mọi mặt trận ngay lập tức (không độ trễ).

File này được viết siêu đơn giản để **ai chưa từng lập trình cũng có thể làm được**. Hãy làm theo từng bước nhé!

---

## 🛠️ PHẦN 1: CÁC BƯỚC CÀI ĐẶT LẦN ĐẦU
Chỉ cần làm một lần duy nhất lúc mới đem Bot về máy.

### Bước 1: Cài đặt phần mềm nền tảng
1. Tải và cài đặt **Python** (Bản 3.10 trở lên) tại trang chủ `python.org`.
   > **Lưu ý CỰC KỲ QUAN TRỌNG:** Lúc cài đặt, ở màn hình đầu tiên, nhớ tích dấu tick ✔️ vào ô `"Add Python to PATH"` ở dưới cùng.
2. Tải toàn bộ mã nguồn Bot này về máy, giải nén vào một thư mục (Ví dụ: `D:\Auto post news`).

### Bước 2: Cài đồ nghề cho Bot
1. Mở cửa sổ Terminal (hoặc Command Prompt / PowerShell) lên.
2. Diễu hành đến thư mục chứa Bot bằng lệnh `cd "D:\Auto post news"` (Thay bằng đường dẫn của bạn).
3. Gõ lệnh sau rồi bấm Enter, máy tính sẽ tự động cắm rễ các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```
   *(Nếu bị lỗi lệnh pip, hãy thử: `python -m pip install -r requirements.txt`)*

---

## 🔑 PHẦN 2: CHÌA KHÓA VÀ CẤU HÌNH BẢO MẬT (`.env`)

Bot cần các loại chìa khóa để chạy: Bộ não AI, Quyền đăng bài Mạng Xã Hội, và Cổng nghe tin Telegram.
Hãy **TẠO MỘT TỆP MỚI** ngay trong thư mục Bot, đặt tên chính xác là `.env` (chú ý có dấu chấm ở đầu). Mở nó lên bằng Notepad và điền vào các thông tin sau:

*(Tuyệt đối giữ bí mật file `.env` này!)*

```env
# ----- 1. CHÌA KHÓA BỘ NÃO AI -----
# (Bắt buộc phải có 1 trong 2)
LLM_PROVIDER=gemini
GEMINI_API_KEY=điền_key_gemini_vào_đây
OPENAI_API_KEY=điền_key_openai_vào_đây_nếu_có

# ----- 2. CHÌA KHÓA MẠNG XÃ HỘI (Nơi Đăng) -----
# Twitter / X
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# Telegram Bot (Gửi tin vào Group/Channel của bạn)
TELEGRAM_BOT_TOKEN=8769006...
TELEGRAM_CHAT_ID=-100123...

# Facebook Fanpage
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=

# ----- 3. CỔNG NGHE LÓNG TELEGRAM (Dành cho Express Lane cực nhanh) -----
# Lấy api_id và api_hash tại: https://my.telegram.org/
TG_API_ID=điền_số_ID_vào_đây (vd: 1234567)
TG_API_HASH=điền_chuỗi_hash_vào_đây
TG_PHONE=+8498xxxxxxx
# Kênh nguồn muốn theo dõi (Vd: @Coin369, hoặc ID băng số định dạng)
TG_SOURCE_CHANNEL=@KenhTinNhanhCuaBan

# ----- 4. HỆ THỐNG ĐIỀU KHIỂN CHÍNH (Tùy Chọn) -----
# Bạn có thể đổi chữ True thành False để tắt luồng tương ứng
RSS_ENABLED=True
EXPRESS_ENABLED=True
FINGERPRINT_WINDOW_MINUTES=60
EXPRESS_THROTTLE_MINUTES=3
```

**Mẹo tìm chìa khóa dễ dàng:**
- **Gemini (Miễn phí):** Vào `aistudio.google.com/app/apikey` tạo 1 key. Nhanh gọn nhẹ.
- **Telegram Bot:** Chat với `@BotFather` trên Telegram để tạo Bot lấy Token. Sau đó thêm Bot vào Group của bạn. Tìm con bot `@RawDataBot` gõ lệnh để lấy Chat ID nhóm.
- **Telegram Express ID (Nghe lóng):** Đăng nhập số điện thoại của bạn vào `my.telegram.org`, chọn "API development tools" để lấy `TG_API_ID` và `TG_API_HASH`.

---

## 🚀 PHẦN 3: BẬT NGUỒN VÀ LÁI BOT THỰC TẾ

Trước khi chạy thật, bạn nên mở file `config.py` bằng Notepad lướt qua để kiểm soát luật chơi:

### Bật / Tắt các Nền Tảng Đăng Bài (Luồng Nào Đăng Kênh Nào?)
Mở tệp `config.py` bằng Notepad, tìm đến mục `PLATFORM_MAPPING`. Đây là nơi phân luồng siêu cấp! Bạn quy định luồng tin khẩn cấp (EXPRESS) hoặc báo mạng (RSS) được phép đăng lên đâu.

Ví dụ dưới đây, Express (Tin Telegram siêu tốc) sẽ chỉ bắn sang nhóm Telegram của bạn. Còn RSS (tin mạng chậm) thì được đăng ở cả Telegram lẫn Twitter/X:

```python
# --- CÔNG TẮC ĐIỀU KHIỂN NỀN TẢNG (PLATFORM MAPPING) ---
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS": ["telegram", "twitter"]  # Có thể đổi mảng rỗng [] để tắt
}
```

### 2. Chế Độ Nháp "Bắn Chỉ Thiên" (Cực kỳ khuyên dùng lần đầu)
Tìm mục `TWITTER_CONFIG`. 
Chỉnh dòng `"dry_run": False,` thành `"dry_run": True,`. 
Khi bật `True`, Bot chạy y như thật, đọc tin, sinh bài AI, nhưng tới lúc đăng lên MXH thì nó chỉ **IN RA MÀN HÌNH** cho bạn chấm điểm xem hay không chứ không đăng lên mạng. 

### 3. Khởi Chạy Bộ Ngắt Động Cơ
Mở Terminal ở thư mục bot, gõ lịnh quyền lực nhất:

```bash
python main.py
```

**Thế là xong! Mọi thứ diễn ra tự động:**
1. Màn hình sẽ chẻ làm 2 luồng. **Express Listener** màu xanh lóe lên kết nối thẳng vào luồng chat Telegram của bạn. Chờ đợi tin giật gân. *(Lần chạy đầu tiên, màn hình đen có thể sẽ hỏi Mã Code Telegram gửi về điện thoại, hãy nhập vào)*.
2. **RSS Lane** chạy 15 phút 1 lần. Đọc báo -> Diệt tin trùng -> Xếp hạng điểm -> Lấy tin cao nhất nhờ AI tóm tắt -> Đăng!
3. 🔥 **Siêu Năng Lực Hot-Reload:** Bạn đang bật Bot nhưng thấy nó post nhanh quá? Cứ việc ở ngoài Notepad sửa file `.env` (vd: `RSS_ENABLED=False`) rồi ấn SAVE. Ngôi sao kíp nổ của Bot sẽ tự nhận diện thiết đặt mới ngay lập tức mà **Không Cần Khởi Động Lại!**

---

## ⚙️ PHẦN 4: NGHỆ THUẬT ĐỘ BOT (DÀNH CHO CHỦ TỌA BIÊN TẬP)

Sự thông minh của Bot nằm ở file `config.py`. Bạn hoàn toàn được phép sửa chữ ở các vùng sau:

### 1. Dạy Bot bắt "Từ Khóa Vàng" (Mục `SCORING_WEIGHTS`)
Hãy định nghĩa lại thế giới quan của Bot:
- **`keyword_categories`**: Đây là rổ từ khóa. Ví dụ các từ khóa thuộc nhóm `market_moving` (như "hack", "funding", "listing") sẽ được điểm rất cao. Nhóm `price_analysis` (như "analyst predicts", "price target") sẽ bị điểm âm.
- **`keyword_caps`**: Chỉnh điểm trần. Từ khóa `market_moving` xứng đáng lọt top được cấp dải điểm rộng (15.0).
- **`major_tokens` / `major_exchanges`**: Đây là bộ lọc Token-Aware (Siêu Tính Năng). Nếu bài báo có nhắc đến tên Token/Sàn ở đây, *CỘNG THÊM* từ khóa Market Moving -> *Cộng ngay 2.0đ Thưởng*. Ngược lại, Tên Token *CỘNG THÊM* bài viết sặc mùi Đầu cơ phân tích chiều giá -> *Trừ ngay 10.0đ Phạt* (giết rank ngay lập tức).
- **`editorial_verbs`**: Các động từ mạnh mẽ báo hiệu tin nóng nổ ra. Nếu báo đưa tựa đề có chữ `"hacked"`, cộng 4.5 điểm!

### 2. Định Hình Nét Chữ AI (Mục `PROMPT_TEMPLATES`)
Hệ thống nay đã chia làm 2 bộ não: Não tin hỏa tốc (EXPRESS) và Não tin sâu (RSS). Bạn có thể đổi văn phong từng não riêng biệt:

Trong `config.py`, tìm mảng `PROMPT_TEMPLATES`.
- Bạn muốn tin mạng (RSS) nghiêm túc? Đừng sửa phần của "RSS".
- Bạn muốn tin chớp nhoáng từ Telegram (EXPRESS) nghe hoảng hốt, cấp bách? Hãy thay đổi phần "EXPRESS":

```python
"EXPRESS": (
    "Bạn là một Admin Channel siêu cháy. Hãy viết tin Break siêu giật gân, dùng cực nhiều icon lửa cháy 🚨🔥, cảnh báo fomo ngay! Kết bài kêu hashtag #GOGOGO"
),
```

Thế là ra siêu phẩm! Điểm mạnh là RSS vẫn giữ nguyên vẻ điềm đạm, chỉ dòng tin Express là hóa điên!

### 3. Nạp Thêm Nguồn Báo Tùy Thích (Mục `RSS_SOURCES`)
Sửa hoặc copy dán thêm các Rss feed mới:
```python
{
    "id": "cafef_taichinh",             
    "name": "CafeF Tài Chính",          
    "url": "https://cafef.vn/tai-chinh.rss",  
    "credibility_score": 1.2, # Hệ số tin cậy. Nếu báo này xịn, cho nó 1.5. Nếu báo hay câu view, cho 0.8 để dìm điểm nó xuống!
    "latency_advantage_score": 1.0     
}
```

Chúc bạn sở hữu cỗ máy hút Tráfico tự động bá đạo nhất MXH! 🚀
