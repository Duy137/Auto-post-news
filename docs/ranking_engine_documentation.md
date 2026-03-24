# Hệ Thống Chấm Điểm Ranking Engine (V3.1 - Enhanced Business & Security Filter)

Tài liệu này cung cấp cái nhìn chi tiết nhất về cơ chế chấm điểm tin tức của hệ thống `Auto-post-news`. Phiên bản V3.1 tập trung vào việc tách biệt các loại sự kiện khác nhau để tối ưu hóa khả năng đưa tin thị trường và giảm thiểu rác truyền thông.

---

## 🏗️ 1. Công Thức Chấm Điểm Tổng Quát

`Total Score = Editorial_Score * Time_Decay * Topic_Novelty_Penalty`

Trong đó:
*   **Editorial Score**: Điểm chất lượng nội dung (Dựa trên Từ khóa, Dòng tiền và Thực thể).
*   **Time Decay**: Hệ số hao mòn theo thời gian (Tin cũ mất điểm).
*   **Topic Novelty Penalty**: Chế tài chống trùng lặp chủ đề (Supression Guard).

---

## 🎯 2. Logic Biên Tập & Phân Loại Keyword (Editorial Score)

Đây là thành phần quan trọng nhất, được cấu hình tại `config.py`.

### A. Rổ Từ Khóa & Giới Hạn (Keyword Caps)
Điểm số được tính bằng cách quét các rổ từ khóa. Mỗi rổ có một **Trần điểm (Cap)** để tránh việc một bài báo có quá nhiều từ khóa cùng loại gây "lạm phát" điểm.

| Rổ Keyword | Cap (Điểm) | Ý Nghĩa / Mục Tiêu |
| **Market Moving** | 10.0 | Thay đổi vĩ mô/thị trường (ETF, Regulation, Rate). Khác với V3 cũ, các từ khóa luật pháp đã được dời đi. |
| **Macro Politics** | 10.0 | Kinh tế biểu mô, lãi suất (Powell, FOMC, CPI, Election, SEC). |
| **Major Tech** | 8.0 | Nâng cấp giao thức mạng lưới (Mainnet, Protocol, Roadmap). |
| **Negative Event** | 10.0 | **[NEW MIGRATION]** Tích hợp từ Rổ Security cũ và Legal Keywords. Bao gồm: Hack, Exploit, Scam, Lawsuit, Sued, Charges, Arrest, Downtime. Cần Core Entity để thoát án phạt. |
| **Business/Dev** | 10.0 | Dự án phát triển (Funding, Launch, Series A, Partnership). |
| **Price Analysis** | **-18.0** | **Rổ Phạt (Penalty)**: Phân tích kỹ thuật, dự đoán giá, tin đồn, lùa gà. |

### B. Refined Entity-Based Scoring (V3.2.1)
Hệ thống sử dụng danh sách thực thể hợp nhất để lọc nhiễu một cách thông minh:
*   **Unified Entities**: Tự động kết hợp `major_tokens`, `major_exchanges` và `core_entities` (SEC, Fed, Powell...).
*   **Cơ chế Phạt chọn lọc**: Hình phạt rớt điểm chỉ áp dụng cho các rổ "Hành động liên quan 1 Project cụ thể" (`Negative Event`, `Business Dev`, `Major Tech`).
*   **Danh sách Miễn trừ (Exempt)**: Các rổ "Tác động toàn thị trường" (`Market Moving`, `Macro / Politics`) **KHÔNG** bị phạt.
*   **Lý do cho việc dịch chuyển Legal Keywords**: Vấn đề pháp lý (kiện tụng, bắt bớ) hay lỗi server (sập mạng lưới) luôn gắn liền với dự án cụ thể. Nếu tòa án kiện một dự án vô danh -> Nhận án phạt 60%. Nếu Binance/SEC kiện nhau -> Thoát án phạt lên trang đầu.
*   **Thông số điều chỉnh**: `non_core_penalty_multiplier` (Mặc định **0.4** - giữ lại 40% điểm).
*   **Mục tiêu**: Đảm bảo tin tức vĩ mô quan trọng không bao giờ bị bỏ lỡ, trong khi dự án cỏ bị đào thải mạnh.

### C. Contextual Filter (Gỡ Hình Phạt)
Hệ thống có khả năng phân biệt tin "Thầy dùi" (chỉ báo giá) và tin "Sự kiện" (giá chạy vì có tin thật).
*   **Logic**: Nếu bài viết dính penalty `price_analysis` nhưng đồng thời chứa sự kiện thật (như `negative_event` hay `market_moving`).
*   **Kết quả**: Hình phạt của rổ `Price Analysis` sẽ bị **giảm 70%**.

### D. Token-Aware Scoring (Nhận Diện Token)
Hệ thống ưu ái các Token/Sàn giao dịch lớn trong danh sách `major_tokens` và `major_exchanges`:
*   **Thưởng (+2.0)**: Nếu bài báo là tin sự kiện thực tế (Market Moving/Security) về một Major Entity.
*   **Phạt (-10.0)**: Nếu bài báo chỉ là phân tích giá (Price Analysis) về một Major Entity mà không có sự kiện thật. Điều này triệt tiêu các bài tin đồn "Khi nào BTC lên 100k".

---

## 🌪️ 3. Dòng Tiền (Capital Flow)

*   **Advanced Capital Flow**: Quét Regex tìm các con số tài chính lớn ($50M, 1000 BTC). Nếu khớp, cộng ngay **+4.0** điểm. Tính năng này giúp các tin gọi vốn lớn dễ dàng vươn lên top.

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
1.  Kiểm tra xem nó có chứa Keyword nào trong rổ `market_moving` hoặc các danh mục chính không.
2.  Nếu không, hãy thêm keyword nòng cốt của sự kiện đó vào `market_moving`.
3.  Nếu tin đó về một đồng coin/dự án mới, cân nhắc thêm nó vào `core_entities` để được hưởng đầy đủ điểm số.
