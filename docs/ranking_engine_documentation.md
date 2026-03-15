# Hệ Thống Chấm Điểm Ranking Engine (V4.0 - Tiered & Context-Aware)

Chào Kiến trúc sư và Người vận hành,

Tài liệu này giải thích chi tiết toàn bộ cơ chế hoạt động của `modules/rank.py`. Phiên bản 4.0 giới thiệu khả năng **Phân tầng ưu tiên (Tiered Priority)** và **Bộ lọc ngữ cảnh (Contextual Filter)** để giải quyết triệt để bài toán: *Làm sao để ưu tiên tin cực nóng nhưng không bị phạt oan khi bài tin đó có chứa từ khóa liên quan đến biến động giá.*

---

## 🏗️ 1. Cấu Trúc Tổng Thể (The Formula)

Điểm số bài báo (Final Score) được tính dựa trên lõi Biên Tập nhân với các hệ số Viral và Decay:
`Total Score = (Base + Editorial_Score) * Viral_Potential * Time_Decay * Source_Credibility`

---

## 🎯 2. Logic Phân Tầng & Chấm Điểm (Tiered Scoring)

### Tier 1: Sự kiện Ưu Tiên Tuyệt Đối (Priority Events)
Hệ thống định nghĩa rổ `priority_event` trong `config.py` dành cho các tin "bom tấn":
*   **Hành động pháp lý:** SEC Investigation, Lawsuit, Subpoena.
*   **Sự cố bảo mật:** Hack, Exploit, Breach.
*   **Vận hành sàn:** Halt withdrawals, Suspend trading.
=> Các bài này được cộng điểm cực lớn và **luôn có log Debug** để theo dõi.

### Tier 2: Dòng Tiền Lớn (Advanced Capital Flow)
Sử dụng Regex thông minh để phát hiện các con số triệu/tỷ USD hoặc ETH/BTC lớn (Ví dụ: "$50M", "10,000 ETH").
*   **Thưởng nóng (+4.0đ):** Cho bất kỳ bài nào chứa bằng chứng về dòng tiền lớn.

### Tier 3: Token-Aware Logic
*   **Thương hiệu lớn (+2.0):** Thưởng nếu bài liên quan đến Top Tokens/Exchanges có kèm sự kiện thực tế.
*   **Thầy dùi (-10.0/-12.0):** Phạt nặng nếu nhắc đến Token nhưng nội dung chỉ là phân tích giá.

---

## 🛡️ 3. Bộ Lọc Speculation Hai Lớp (Two-Layer Filter)

Để tiêu diệt tin rác đầu cơ nhưng không giết nhầm tin tốt, hệ thống dùng 2 lớp:

1.  **Lớp 1: Chặn Cứng (Hard Reject):**
    Quét qua `SPECULATION_HARD_REJECT_PATTERN`. Nếu tiêu đề chứa cụm từ như "Price Prediction", "Price Target", "Forecast $...", hệ thống **vứt bài ngay lập tức** (điểm -999.0).
2.  **Lớp 2: Phạt Mềm & Bộ lọc Ngữ Cảnh (Contextual Filter):**
    Bình thường, các từ như "Surge", "Rally", "Plunge" sẽ bị phạt nặng (**-18.0đ**).
    **TUY NHIÊN:** Nếu bài báo đó **VỪA** có từ biến động giá, **VỪA** có từ khóa thuộc nhóm `priority_event` (Ví dụ: "Bitcoin surges after ETF Approval"), hệ thống sẽ tự động **giảm 70% mức phạt**. Điều này giúp các tin tức quan trọng có biến động giá đi kèm vẫn được đăng.

---

## 🌪️ 4. Sức Mạnh Lan Truyền (Viral Potential)
... (Giữ nguyên cơ chế Momentum và Shock Score) ...

---

## ⏳ 5. Quan sát & Tinh chỉnh (Observability)

Phiên bản này bổ sung log `📊 [RANK DEBUG]` chi tiết từng thành phần:
- Xem cụ thể điểm thưởng Keyword, điểm thưởng Dòng tiền, và điểm phạt bị giảm nhờ Context Filter.
- **Quy tắc vàng:** Nếu tin rác vẫn lọt, chỉ cần thêm từ khóa vào rổ `price_analysis` hoặc cập nhật Regex `SPECULATION_HARD_REJECT_PATTERN` trong `config.py`.
�� không bao giờ bùng nổ vượt quá mức cho phép (Khóa khung nhân tử từ `0.7x` đến `1.8x`).

---

## ⏳ 4. Thối Rữa Thời Gian & Uy Tín (Decay & Credibility)

*   **Time Decay:** Công thức hàm nón lá (Exponential Decay). Cứ mỗi giờ trôi qua kể từ lúc báo xuất bản, hệ số điểm sẽ giảm dần đều. Một tin dù nóng cỡ nào nhưng xảy ra cách đây 3 ngày thì kết quả phép nhân = `0.something` -> Đưa nó về cát bụi để chừa sóng cho tin Break hôm nay.
*   **Uy tín (Credibility):** CoinTelegraph (Hệ số `1.15x`) sẽ luôn thắng thế một trang blog vô danh (Hệ số `1.0x`) nếu cùng đưa 1 nội dung.

---

## Tính Ứng Dụng Dành cho Vận Hành:
Làm thế nào để tinh chỉnh hướng đi của hệ thống nếu tin rác vẫn lọt vào lưới?
=> Cực kỳ đơn giản: Bạn CHỈ CẦN mở `config.py` và ném từ khóa rác đó vào rổ `price_analysis`. Thuật toán Toán học ở `rank.py` sẽ lo mọi khâu hành quyết còn lại. Hệ thống vĩnh viễn không cần thay đổi source code ở lõi.
