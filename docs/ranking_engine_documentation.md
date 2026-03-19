# Hệ Thống Chấm Điểm Ranking Engine (V3.0 - Token-Aware & Context Filter)

Chào Kiến trúc sư và Người vận hành,

Tài liệu này giải thích chi tiết toàn bộ cơ chế hoạt động của `modules/rank.py` và cách chúng ta "dạy" hệ thống nhận diện tin tức thông qua `config.py`. Hệ thống được thiết kế hoàn toàn theo logic **Chấm điểm tất định (Deterministic Scoring)**, không sử dụng LLM ở bước phân loại để thiết lập độ tin cậy tuyệt đối và chống lại rác đầu cơ.

Mục tiêu tối thượng của Ranking Engine: **Đưa tin tức sự kiện thực sự tác động đến thị trường (Market-Moving Events, SEC, Hacks) lên Top 1, đồng thời tiêu diệt thẳng tay các bài viết sặc mùi nhận định, dự đoán giá (Price Speculation).**

---

## 🏗️ 1. Cấu Trúc Tổng Thể (The Formula)

Điểm số cuối cùng của mỗi bài báo (Final Score) được tính qua công thức:
`Total Score = (Base + Editorial_Score) * Viral_Potential * Time_Decay * Source_Credibility * Throttling_Penalty`

Trong đó:
*   `Base`: Điểm sàn mặc định.
*   `Editorial_Score`: Điểm biên tập (Trọng tâm của tính năng Phân loại rổ từ khóa, Capital Flow và Token-Aware).
*   `Viral_Potential`: Tiềm năng lan truyền (Chứa Momentum chéo giữa các báo & Cú shock từ vựng).
*   `Time_Decay`: Độ thối rữa theo thời gian (Tin càng cũ càng mất điểm).

---

## 🎯 2. Logic Biên Tập Chống Đầu Cơ (Anti-Speculation)

Thuật toán V3 áp dụng cơ cấu **Lọc Đầu Cơ Hai Lớp (Two-Layer Speculation Filter)** cực kỳ thù hận với rác xả bờ:

### Lớp 1: Bắn Bỏ Tại Chỗ (Hard Reject)
Hệ thống sử dụng `SPECULATION_HARD_REJECT_PATTERN` trong config.
Bất cứ tựa bài nào chứa "price target", "price prediction", "analyst predicts",... sẽ bị gán ngay lập tức điểm **-999.0**.
Bài báo bị vứt bỏ trước khi tốn CPU chạy thuật toán, log in ra `🛑 [FILTERED]`.

### Lớp 2: Phạt Nhẹ & Phạt Mềm (Soft Penalty & Keyword Cap)
Nếu bài báo lọt qua lớp 1 (ví dụ bài ghi "Bitcoin Rallies" hay "ETH Surges"), từ khóa sẽ rơi vào rổ `price_analysis` (Cap phạt: -18.0).
*   **Token-Aware Cắn Trả:** Nếu bài báo có cụm từ "Rally" và cố tình chèn thêm Tên Major Token (BTC, ETH) mà *KHÔNG HỀ* có bất cứ sự kiện thực tế nào đi kèm -> Nó bị dã thêm một đòn `SPECULATION_SOFT_PENALTY_SCORE` (-12.0) nữa. Điểm âm vô cực.

---

## 🛡️ 3. Ưu Tiên Sự Kiện Nhóm 1 & Bộ Lọc Ngữ Cảnh (Contextual Filter)

Để tránh việc "Giết lầm hơn bỏ sót" (Ví dụ tin tức: *"XRP Tăng Vọt (+Phạt) Sau Khi SEC Bãi Bỏ Vụ Kiện (+Thưởng)"*), V3 thiết kế nên **Contextual Filter**.

### Rổ Priority Event (Tier 1)
Nhóm từ khóa VVIP được xác định là thao túng cục diện thị trường (e.g., "Lawsuit", "Hack", "Halt withdrawals", "SEC").
Bài viết chứa nhóm này tự động đẩy form lên cao nhất, không có khái niệm trượt rank.

### Contextual Filter (Gỡ Hình Phạt)
Hàm chấm điểm sẽ kiểm tra Logic:
*Nếu* bài viết bị phạt mảng `price_analysis` (Rally, Surge) *NHƯNG* bài viết có chứa dấu hiệu của `market_moving` hoặc `priority_event` (Ví dụ: Hack, Approval).
**-> Hình phạt bị giảm 70%**.
Cơ chế này hiểu rằng: Token tăng giá LÀ DO một sự kiện có thật. Đây là tin tức giá trị (Đưa tin giá), không phải tin Thầy dùi phím hàng (Nhận định giá).

---

## 💰 4. Theo Dõi Dòng Vốn (Capital Flow Bonus - Tier 2)

Hệ thống tích hợp Regular Expression tinh vi cực mạnh `CAPITAL_FLOW_REGEX` nằm trong config.
Nhiệm vụ: Truy tìm dòng tiền cá voi.
Bất cứ bài báo nào chứa các mệnh giá khổng lồ theo chuẩn: `$50M`, `€100k`, `1000 BTC`, `500k ETH`, `2 Billion USD`.
Hệ thống cộng ngay lập tức một bùa `CAPITAL_FLOW_BONUS` (Mặc định +4.0 điểm). Sự kiện kinh tế sẽ được ưu ái hiển thị.

---

## 🌪️ 5. Hệ Số Lan Truyền (Viral Potential)

Sau khi tính `Editorial_Score`:
*   **Sức Nóng Dư Luận (Cross-Source Momentum):** Nếu SEC kiện Binance, cả CoinTelegraph lẫn CoinDesk đồng loạt đăng trong vài giờ qua -> Thuật toán Jaccard so sánh chéo phát hiện 2 nội dung giống nhau -> Hệ số lây lan (Momentum Score) được cộng dội lên gấp khúc.
*   **Từ vựng Gây Sốc (Shock Score):** Tựa bài chứa "FBI", "Raid", "Emergency" -> Kick-start viral multiplier.

---

## ⚙️ Hướng dẫn Debug cho Vận hành viên

Khi System chạy, nếu có tin tức nào bay vào danh sách "Khá Khẩm" (Score > 8.0) hoặc dính thẻ Priority Event. Hệ thống sẽ tạc thẳng một bảng thông số **`📊 [RANK DEBUG]`** lên Console Terminal.

Ví dụ:
```text
📊 [RANK DEBUG] Article: 'SEC Launches Investigation into Major Crypto Exchange...'
  [+] Base: 8.0 | Editorial Verbs: 4.5 | Source Cred: 1.0
  [+] Kw Bonus: 15.00 | Capital Flow: +0.0 | Token Mod: +2.0
  [-] Penalty: 0.00 | Fatigue: 0.0
  [*] Mults: Viral=1.27 | TimeDecay=2.27
  [*] Keywords Found: ['investigation', 'court', 'lawsuit', 'charges']
  => FINAL_SCORE    : 38.32
```

Dựa vào bảng này, bạn sẽ đọc được lý do tại sao Bot lại Pick bài đó, nó bị trừ bao nhiêu điểm do thối rữa/do đầu cơ, nó lấy được Keyword Bonus từ đâu. Nếu rác lọt lưới, chỉ cần nhét cụm từ rác đó vào rổ `price_analysis` trong file `config.py` và thế là xong! Tương tự, nếu bỏ sót một sự kiện bùng nổ, hãy thêm từ khóa đó vào `priority_event`.
