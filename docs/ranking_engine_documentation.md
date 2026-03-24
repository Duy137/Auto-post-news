# Hệ Thống Chấm Điểm Ranking Engine (V3.1 - Enhanced Business & Security Filter)

Tài liệu này cung cấp cái nhìn chi tiết nhất về cơ chế chấm điểm tin tức của hệ thống `Auto-post-news`. Phiên bản V3.1 tập trung vào việc tách biệt các loại sự kiện khác nhau để tối ưu hóa khả năng đưa tin thị trường và giảm thiểu rác truyền thông.

---

## 🏗️ 1. Công Thức Chấm Điểm Tổng Quát

Điểm số hành trình của một bài báo từ lúc thu thập đến khi được đăng:

`Total Score = (Editorial_Score) * Viral_Potential * Time_Decay * RSS_Suppression`

Trong đó:
*   **Editorial Score**: Điểm chất lượng nội dung biên tập.
*   **Viral Potential**: Hệ số tiềm năng lan truyền (Momentum + Shock).
*   **Time Decay**: Hệ số thối rữa theo thời gian (Tin cũ mất điểm).
-   **RSS Suppression**: Hệ số chống trùng lặp chủ đề (Chế tài nếu vừa đăng tin tương tự).

---

## 🎯 2. Logic Biên Tập & Phân Loại Keyword (Editorial Score)

Đây là thành phần quan trọng nhất, được cấu hình tại `config.py`.

### A. Rổ Từ Khóa & Giới Hạn (Keyword Caps)
Điểm số được tính bằng cách quét các rổ từ khóa. Mỗi rổ có một **Trần điểm (Cap)** để tránh việc một bài báo có quá nhiều từ khóa cùng loại gây "lạm phát" điểm.

| Rổ Keyword | Cap (Điểm) | Ý Nghĩa / Mục Tiêu |
| :--- | :--- | :--- |
| **Market Moving** | 12.0 | Các sự kiện lớn (ETF, Ban, Regulation, Airdrop). |
| **Priority Event** | 8.0 | Sự kiện khẩn cấp (Hack, Lawsuit, Withdrawal Halt). |
| **Urgent** | 10.0 | Hành động pháp lý mạnh (Sues, Arrest). |
| **Major Tech** | 10.0 | Nâng cấp giao thức (Mainnet, Upgrade, Roadmap). |
| **Business Dev** | 8.0 | Hoạt động kinh doanh (Funding, Launch, Partnership). |
| **Security Incident** | 6.0 | Sự cố an ninh mức độ thấp hoặc scam cá nhân. |
| **Price Analysis** | **-18.0** | **Rổ Phạt (Penalty)**: Phân tích kỹ thuật, dự đoán giá, tin đồn. |

### B. Contextual Filter (Gỡ Hình Phạt)
Hệ thống có khả năng phân biệt tin "Thầy dùi" (chỉ báo giá) và tin "Sự kiện" (giá chạy vì có tin thật).
*   **Logic**: Nếu bài viết dính penalty `price_analysis` (Ví dụ: "BTC Surge") nhưng đồng thời chứa keyword trong `market_moving` hoặc `priority_event` (Ví dụ: "due to ETF approval").
*   **Kết quả**: Hình phạt của rổ `Price Analysis` sẽ bị **giảm 70%**.

### C. Token-Aware Scoring (Nhận Diện Token)
Hệ thống ưu ái các Token/Sàn giao dịch lớn trong danh sách `major_tokens` và `major_exchanges`.
*   **Thưởng (+2.0)**: Nếu bài báo là tin sự kiện thực tế (Market Moving/Priority) về một Major Entity.
*   **Phạt (-12.0)**: Nếu bài báo chỉ là phân tích giá (Price Analysis) về một Major Entity mà không có sự kiện thật.

---

## 🌪️ 3. Hệ Số Lan Truyền & Dòng Tiền (Viral & Capital)

*   **Advanced Capital Flow**: Quét Regex tìm các con số tài chính lớn ($50M, 1000 BTC). Nếu khớp, cộng ngay **+4.0** điểm.
*   **Cross-Source Momentum**: Nếu CoinTelegraph và CoinDesk cùng đăng một chủ đề trong 1-2 giờ qua, hệ số Viral sẽ tăng mạnh do thuật toán phát hiện sự đồng nhất (Jaccard Similarity).
*   **Shock Score**: Thưởng điểm cho các từ gây sốc: *FBI, Raid, Emergency, Bankruptcy*.

---

## 📈 4. Đánh giá Hệ thống (SWOT Analysis)

### ✅ Điểm Mạnh (Strengths)
1.  **Tốc độ & Hiệu năng**: Chấm điểm tất định (Deterministic), không tốn chi phí và thời gian gọi AI (LLM) ở bước lọc.
2.  **Khả năng Chống Rác (Anti-Spam)**: Lớp Hard Reject (vứt bỏ ngay) và Soft Penalty (trừ điểm nặng) triệt tiêu hiệu quả các bài viết "Clickbait" hoặc dự đoán giá ảo.
3.  **Ưu tiên Dòng Tiền**: Nhận diện rất tốt các chuyển động tiền tệ lớn (Cá voi, Quỹ đầu tư).
4.  **Tự Động Diversify**: Hệ số `RSS_Suppression` ngăn chặn việc Telegram bị "spam" bởi 10 bài báo khác nhau nhưng cùng nói về 1 sự kiện.

### ❌ Điểm Yếu (Weaknesses)
1.  **Keyword Overlap**: Một số từ khóa trung tính (như "Launch") có thể xuất hiện trong cả tin rác quảng cáo và tin công nghệ lớn.
2.  **Phụ thuộc vào Major Entity List**: Nếu một dự án mới nổi (không nằm trong `major_tokens`) gặp sự kiện lớn, nó sẽ không nhận được Token Bonus.
3.  **Khó nhận diện Ngữ cảnh Tiếng Anh phức tạp**: Vì chỉ quét Keyword đơn lẻ/Regex, hệ thống đôi khi bị đánh lừa bởi các tiêu đề lắt léo về mặt ngữ nghĩa (Sarcasm, Irony).
4.  **False Positives (Cận Crypto)**: Các tin tức về công nghệ/tài chính truyền thống (như vụ Coupang, Data Breach của công ty bán lẻ) có thể bị nhầm là tin Crypto nếu trùng keyword an ninh.

---

## 🛠️ Hướng Dẫn Tối Ưu Cho Vận Hành

Nếu bạn thấy tin rác lọt lưới:
1.  Copy cụm từ đặc trưng của tin rác đó.
2.  Thêm nó vào rổ `price_analysis` hoặc `SPECULATION_HARD_REJECT_PATTERN` trong `config.py`.
3.  Nếu đó là tin rác quảng cáo dự án, hãy thêm tên dự án đó vào rổ `price_analysis` để hệ thống tự động dìm điểm.

Nếu bạn thấy tin quan trọng bị bỏ sót:
1.  Kiểm tra xem nó có chứa Keyword nào trong rổ `priority_event` không.
2.  Nếu không, hãy thêm keyword nòng cốt của sự kiện đó vào `priority_event`.
