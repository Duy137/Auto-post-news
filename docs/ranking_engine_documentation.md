# Hệ Thống Chấm Điểm Ranking Engine (V3.0 - Token-Aware)

Chào Kiến trúc sư và Người vận hành,

Tài liệu này giải thích chi tiết toàn bộ cơ chế hoạt động của `modules/rank.py` và cách chúng ta "dạy" hệ thống nhận diện tin tức thông qua `config.py`. Hệ thống được thiết kế hoàn toàn theo logic **Chấm điểm tất định (Deterministic Scoring)**, không sử dụng LLM ở bước phân loại để tiết kiệm chi phí và đảm bảo tốc độ tuyệt đối.

Mục tiêu tối thượng của Ranking Engine: **Đưa tin tức thực sự tác động đến thị trường (Market-Moving Events) lên Top 1, đồng thời tiêu diệt toàn bộ các bài viết sặc mùi nhận định, dự đoán giá (Price Speculation & Analysis).**

---

## 🏗️ 1. Cấu Trúc Tổng Thể (The Formula)

Điểm số cuối cùng của mỗi bài báo (Final Score) được tính qua công thức:
`Total Score = (Base + Editorial_Score) * Viral_Potential * Time_Decay * Source_Credibility`

Trong đó:
*   `Base`: Điểm sàn mặc định (Luôn = 3.0)
*   `Editorial_Score`: Điểm biên tập (Trọng tâm của tính năng Token-Aware mới).
*   `Viral_Potential`: Tiềm năng lan truyền (Chứa Momentum & Cú shock từ vựng).
*   `Time_Decay`: Độ thối rữa theo thời gian (Tin càng cũ càng mất điểm).

---

## 🎯 2. Lõi Chấm Điểm Biên Tập (Editorial Score & Token-Aware Logic)

Đây là nơi hệ thống quyết định bài báo có "chất" hay không. Tín hiệu được lấy từ cấu hình `SCORING_WEIGHTS` trong `config.py`.

### A. Rổ Từ Khóa (Keyword Categories & Caps)
Chúng ta chia từ khóa thành nhiều "Rổ" (Categories). Mỗi từ khóa khi xuất hiện sẽ được cộng điểm, NHƯNG tổng điểm của một rổ không bao giờ được vượt quá "Điểm Trần" (Cap) để chống lạm phát điểm nếu một bài viết nhồi nhét quá nhiều từ khóa.

*   **Rổ `market_moving` (Cap: 15.0)**: Chứa các sự kiện thay đổi cuộc chơi như Hacks, Funding lớn, Listing, Kiện tụng SEC,... Được ưu tiên điểm cao nhất.
*   **Rổ `macro_politics` (Cap: 12.0)**: Chứa luật lệ, vĩ mô, lãi suất.
*   **Rổ `major_tech` (Cap: 10.0)**: Chứa công nghệ lõi như Mainnet, Hardfork.
*   **Rổ `price_analysis` (Cap: -6.0)**: KHU VỰC CẤM! Chứa các từ "analyst predicts", "price target". Khi quét trúng, điểm số ngay lập tức **bị trừ**.

### B. Động Từ Biên Tập (Editorial Verbs)
Xếp hạng các động từ hành động mạnh (như "approve", "enforce", "announce") vào đầu tựa bài sẽ được cộng dồn (Max 4.0đ). Càng hành động, điểm càng cao.

### 🌟 C. Cơ Chế Thưởng/Phạt thông minh: Token-Aware
Hệ thống không đánh đồng mọi bài báo có nhắc đến Bitcoin. Nó quan tâm đến **bối cảnh**. Trong `config.py` định nghĩa 2 danh sách khổng lồ: `MAJOR_TOKENS` (Top 45+) và `MAJOR_EXCHANGES` (Top 14+).

Hàm tính điểm sẽ soi: Bài báo có nhắc đến Tên Token/Sàn hay không?
*   **Cộng cồng kềnh (+2.0)**: Nếu bài có Tên Token + Rơi vào rổ `market_moving` (Ví dụ: "OKX nhận đầu tư 100 Triệu USD").
*   **Trảm lập quyết (-10.0)**: Nếu bài có Tên Token + Rơi vào rổ `price_analysis` (Ví dụ: "Solana chuẩn bị bật tăng lên 500$, theo lời chuyên gia"). Mức phạt -10.0đ này sẽ dìm bài báo xuống đáy bảng xếp hạng vĩnh viễn, ngăn không cho gửi cặn bã tới LLM tóm tắt.

*(Ngoài ra hệ thống còn chặn cứng ở vòng ngoài bằng `SPECULATION_REJECT_PATTERN` đối với cụm từ quá rõ ràng, đánh điểm `-999.0` để Vứt Bài Ngay Lập Tức mà không cần tốn CPU tính toán).*

---

## 🌪️ 3. Hệ Số Lan Truyền (Viral Potential)

Sau khi tính được "Chất lượng" bài viết ở mục 2, hệ thống nhân nó với sức lây lan:

*   **Sức Nóng Dư Luận (Cross-Source Momentum):** Nếu cùng một sự kiện (ví dụ: SEC kiện Binance) mà cả CoinTelegraph lẫn CoinDesk đều đồng loạt đăng trong vài giờ qua -> Thuật toán Jaccard sẽ so sánh chéo, nhận diện đây là tin cực chấn động và nhân vọt hệ số lan truyền cho CẢ HAI bài viết.
*   **Từ vựng Gây Sốc (Shock Score):** Bơm một chút hệ số nếu tựa đề chứa những từ ngắn gắt gỏng ("Halt", "FBI", "Raid", "Emergency").

Tất cả độ lây lan này bị nhốt trong hàm Sigmoid để hệ số không bao giờ bùng nổ vượt quá mức cho phép (Khóa khung nhân tử từ `0.7x` đến `1.8x`).

---

## ⏳ 4. Thối Rữa Thời Gian & Uy Tín (Decay & Credibility)

*   **Time Decay:** Công thức hàm nón lá (Exponential Decay). Cứ mỗi giờ trôi qua kể từ lúc báo xuất bản, hệ số điểm sẽ giảm dần đều. Một tin dù nóng cỡ nào nhưng xảy ra cách đây 3 ngày thì kết quả phép nhân = `0.something` -> Đưa nó về cát bụi để chừa sóng cho tin Break hôm nay.
*   **Uy tín (Credibility):** CoinTelegraph (Hệ số `1.15x`) sẽ luôn thắng thế một trang blog vô danh (Hệ số `1.0x`) nếu cùng đưa 1 nội dung.

---

## Tính Ứng Dụng Dành cho Vận Hành:
Làm thế nào để tinh chỉnh hướng đi của hệ thống nếu tin rác vẫn lọt vào lưới?
=> Cực kỳ đơn giản: Bạn CHỈ CẦN mở `config.py` và ném từ khóa rác đó vào rổ `price_analysis`. Thuật toán Toán học ở `rank.py` sẽ lo mọi khâu hành quyết còn lại. Hệ thống vĩnh viễn không cần thay đổi source code ở lõi.
