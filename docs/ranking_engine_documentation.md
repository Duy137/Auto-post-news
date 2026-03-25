# Hệ Thống Chấm Điểm Ranking Engine (V4.4 - Asset Tiering & Context-Aware)

Tài liệu này cung cấp cái nhìn chi tiết nhất về cơ chế chấm điểm tin tức của hệ thống `Auto-post-news`. Ở phiên bản V4.4, hệ thống đã tiến hóa thành một cỗ máy lọc nhiễu tinh vi, loại bỏ hoàn toàn rác SEO, tin TradFi (tài chính truyền thống), và tin "thầy dùi" dự đoán giá.

---

## 🏗️ 1. Công Thức Chấm Điểm Tổng Quát

> `Total Score = (Editorial_Score + Trend_Bonus + Capital_Flow_Bonus) * Time_Decay * Topic_Novelty_Penalty`

Trong đó:
*   **Editorial Score**: Điểm chất lượng nội dung cốt lõi, tích lũy từ các rổ từ khóa (Base Score mặc định: `3.0`).
*   **Trend Bonus**: Điểm Lan Truyền. Thưởng điểm nếu có nhiều báo cùng đưa tin.
*   **Capital Flow Bonus**: Thưởng điểm Dòng Tiền. Kích hoạt khi nhắc tới số tiền >= $50 Triệu.
*   **Time Decay**: Hệ số hao mòn theo thời gian (Tin càng cũ điểm càng tụt).
*   **Topic Novelty Penalty**: Chế tài chống trùng lặp. Phạt điểm những cụm từ khóa đã xuất hiện quá nhiều lần trong 24h.

---

## 🎯 2. Logic Cộng Dồn Đa Điểm & Rổ Keyword

Hệ thống hoạt động theo nguyên tắc **Cộng dồn xuyên Rổ (Cross-Bucket Accumulation)** nhưng **Áp trần nội bộ (Internal Bucket Cap)**.
- Nếu bài báo đánh trúng từ khóa ở 2 rổ khác nhau (Ví dụ: `market_moving` và `business_development`), điểm sẽ được **cộng dồn** ăn Combo.
- Nếu bài báo nhồi nhét nhiều từ khóa trong **cùng 1 rổ**, điểm sẽ bị chặn lại ở **mức Trần (Cap)** của rổ đó.

| Rổ Keyword | Cap (Tối đa) | Ý Nghĩa / Mục Tiêu |
| :--- | :--- | :--- |
| **Market Moving** | `10.0` | Thay đổi vĩ mô/thị trường (ETF, Regulation, Rate). **Được miễn mọi án phạt.** |
| **Macro Politics** | `10.0` | Chính trị, vĩ mô (SEC, Powell, Election, Fed). **Được miễn mọi án phạt.** |
| **Business / Dev** | `10.0` | Vận hành kinh doanh (Funding, Partnership, Acquisition). Bị phạt nếu không có Core Entity. |
| **Negative Event** | `10.0` | Tin xấu rúng động (Hack, Exploit, Scam, Lawsuit, Banned). Bỏ qua yếu tố pháp lý đơn lẻ. Bị phạt nếu không có Core Entity. |
| **Major Tech** | `8.0` | Nâng cấp mạng lưới (Mainnet, Hard Fork). |
| **Price Analysis** | **-18.0** | **Rổ Phạt (Penalty)**: Phân tích kỹ thuật, dự đoán giá (Hovers, Stuck at, Targets, Predicts). |

---

## 🛡️ 3. Phân Hạng Tài Sản (Asset Tiering Penalty - V4.4)

Báo chí thường xuyên nhồi nhét từ khóa "Bitcoin" hoặc "BTC" vào các bài rác để lách luật. V4.4 xử lý triệt để trò lừa này bằng cách phân hạng tài sản:

Hệ thống sẽ cấp hệ số Phạt (Penalty Multiplier) cho các Rổ bị kiểm soát (Business, Tech, Negative) dựa trên Thực thể (Entity) được nhắc đến:

1. **Ngạch Miễn Nhiễm (Standard Tokens/Macro/Exchanges)**:
   - *Ví dụ:* Solana, XRP, SEC, Binance, BlackRock...
   - *Hệ số:* **1.0** (Không bị phạt).
   - *Lý do:* Rất hiếm khi báo chí bịa chuyện hoặc spam SEO bằng tên Solana hay Circle. Tin tức xài các từ này thường là tin thật.

2. **Ngạch Siêu Nhiễu (Noise Tokens)**:
   - *Ví dụ:* Bitcoin, BTC, Ethereum, ETH.
   - *Hệ số:* **0.7** (Bị phạt 30% tổng điểm rổ).
   - *Lý do:* Từ khóa bị lạm dụng nhất lịch sử. Một tin rác nhắc tới Bitcoin sẽ bị gọt 30% sức mạnh. Để vươn lên Top, bài Bitcoin đó quy định BẮT BUỘC phải đi liền với tín hiệu Dòng tiền Lớn, Trend, hoặc dính Vĩ Mô.

3. **Ngạch Cỏ / TradFi (Non-Core Entities)**:
   - *Ví dụ:* Dự án lạ hoắc, công ty chứng khoán truyền thống, tin Dược phẩm.
   - *Hệ số:* **0.4** (Bị phạt 60% tổng điểm rổ).
   - *Lý do:* Chém thẳng tay các dự án không thuộc hàng ngũ Blue-chip và quét sạch TradFi Bleeds.

---

## 🌪️ 4. Bơm Năng Lượng (Trend & Capital Flow)

*   **Cluster Trend Bonus (V4.1)**: 
    Xác định độ "Hot" bằng Sự đồng thuận của Tòa soạn (Publisher Consensus). Ở khâu lọc trùng lặp, nếu tin tức này được nhiều báo gốc cùng đưa (`cluster_size`), điểm sẽ được thiết lập siêu tốc độ: 
    > `Trend Bonus = (cluster_size - 1) * 1.0`
    Tin càng nhiều báo lớn nhảy vào, điểm tự xưng vương không cần chứng minh.

*   **Advanced Capital Flow (V4.2)**: 
    Chỉ thưởng `+4.0đ` cho các bản tin có Dòng Tiền Tinh Hoa (Whale/Institutional). Bộ quét Regex chỉ nhận diện:
    - Tiền tệ (USD/EUR): Phải lớn hơn hoặc bằng **$50 Triệu** (`$50M`), hoặc tính bằng Tỷ (`Billion / B`).
    - Tiền số (BTC/ETH/SOL): Lớn hơn **100** đơn vị.
    Bộ lọc này chặn đứng các tin gọi vốn $2M-$5M tẻ nhạt của các dự án vi mô.

---

## 🛑 5. Hard Reject & Anomaly Catcher

*   **Bộ Lọc Thầy Dùi (Speculation Hard Reject)**: Bất kỳ bài báo nào dính các cụm từ mồi chài dự đoán (Ví dụ: `price prediction`, `pump and dump`, `ponzi`, `forecast $100k`) sẽ bị vứt thẳng vào sọt rác với số điểm `-999.0`.
*   **Nắn Dòng Môi Trường Cỏ**: Toàn bộ luồng nguồn báo M&A/Chứng khoán chung chung kiểu `investing_stock` hay `cnbc_finance` đã bị gỡ bỏ cứng khỏi Nguồn cung cấp (RSS Feeds) để lọc máu tinh khiết 100% Crypto-Native.

---

## 🤖 6. Cân Bằng Trí Tuệ Nhân Tạo (Cold-Start Calibration)

Tại V4.3, Topic Novelty (Sự mới mẻ của Chủ đề) được gắn sẵn một mức **Tần suất Mỏ neo (Baseline)** từ dữ liệu quét thực tế đo lường 24h:
- `bitcoin`: Mặc định bị tính là đã xuất hiện 75 lần.
- `hack`: Mặc định tính là xuất hiện 5 lần.
Điều này loại bỏ hoàn toàn hiện tượng Ảo giác Cold-Start (khi Database bị xóa, một tin Bitcoin nhạt nhẽo đầu tiên cũng bị hệ thống nhầm là "Sự kiện chưa từng có thế kỷ" và buff điểm láo).

---

## 🕒 7. Hao Mòn Thời Gian Liên Tục (Time Decay)

*   **Công thức**: `exp(-lambda * hours_passed)` (với `lambda = 0.035`).
*   **Ý nghĩa**: Một bài báo ngâm trong hàng đợi 20 giờ sẽ bị bào mòn một nửa số điểm gốc. Do tính toán thả bằng thời gian trôi của Từng Giây, **Không bao giờ có 2 bài báo có điểm bằng nhau tuyệt đối**. Điều kiện Tie-Breaker được chốt chặt về mặt toán học.
