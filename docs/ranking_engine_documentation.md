# Hệ Thống Chấm Điểm Ranking Engine (V4.5)

Tài liệu chi tiết cơ chế chấm điểm tin tức của hệ thống `Auto-post-news`. Phiên bản V4.5 là cỗ máy lọc nhiễu tinh vi nhất, loại bỏ rác SEO, tin TradFi, tin "thầy dùi", và tin chỉ nhắc tên Bitcoin/BTC để lách kiểm duyệt.

---

## 🏗️ 1. Công Thức Chấm Điểm Tổng Quát

Bài báo đi qua 2 cấp tính điểm:

**Cấp 1 — Editorial Score (Điểm Biên Tập Nội dung):**
```
Editorial_Score = (Base_Score + Positive_KW + Penalty_KW + Trend_Bonus) × Source_Credibility
```

**Cấp 2 — Final Score:**
```
Final_Score = Editorial_Score × Time_Decay × Topic_Novelty_Multiplier
```

| Thành phần | Nguồn gốc |
|:---|:---|
| `Base_Score` | Cố định `3.0` cho mọi bài |
| `Positive_KW` | Điểm Rổ Keyword + Entity Bonus + Capital Flow |
| `Penalty_KW` | Điểm phạt từ rổ `price_analysis` và Soft Penalty thầy dùi |
| `Trend_Bonus` | `(cluster_size - 1) × 1.0` — Nhiều báo cùng đưa tin |
| `Source_Credibility` | `credibility_score × latency_advantage_score` từ RSS_SOURCES |
| `Time_Decay` | `exp(-0.035 × hours_passed)` |
| `Topic_Novelty_Multiplier` | `0.1×` nếu topic trùng bài đã đăng trong 60 phút; `1.0` nếu không |

---

## 🎯 2. Các Rổ Keyword & Điểm

Hệ thống hoạt động theo nguyên tắc **Single-Best Bucket (V4.6)** và **Strict 1-Hit (V4.7)** để ngăn chặn lạm phát điểm:
- **Strict 1-Hit:** Điểm mỗi rổ là xác định (Deterministic). Chỉ cần bài báo khớp **1 từ khóa đầu tiên** trong rổ, nó nhận trọn vẹn 100% điểm Cap của rổ đó. Việc nhồi nhét nhiều từ khóa cùng một rổ không có tác dụng cộng dồn.
- **Single-Best Bucket:** Code tính điểm tất cả các rổ, nhưng cuối cùng chỉ lấy **rổ có điểm cao nhất** để cộng vào tổng điểm (Ngăn bài đa chủ đề leo điểm vô lý).

| Rổ Keyword | Cap | Bị Phạt Asset Tiering? | Loại Từ Khóa |
|:---|:---|:---|:---|
| **`market_moving`** | **+7.0** | ❌ Miễn phạt | `etf approval`, `halving`, `institutional inflow`, `buys bitcoin`... |
| **`macro_politics`** | **+8.0** | ❌ Miễn phạt | `fed`, `cpi`, `rate`, `powell`, `sec`, `legislation`, `gdp`... |
| **`business_development`** | **+10.0** | ✅ Bị phạt | `funding`, `partnership`, `acquisition`, `series a`, `launch`... |
| **`negative_event`** | **+10.0** | ✅ Bị phạt | `hack`, `exploit`, `scam`, `lawsuit`, `suspended`... |
| **`major_tech`** | **+6.0** | ✅ Bị phạt | `mainnet`, `hard fork`, `protocol`, `network`, `roadmap`... |
| **`price_analysis`** | **-18.0** | — | `rally`, `surge`, `predicts`, `analyst says`, `targets`, `RSI`... |

---

## 🛡️ 3. Phân Hạng Tài Sản (Asset Tiering - V4.4)

Áp dụng cho điểm các **rổ bị kiểm soát** (`business_development`, `negative_event`, `major_tech`) — **không** áp dụng cho `market_moving` và `macro_politics`.

| Ngạch | Điều kiện phát hiện | Bucket Multiplier |
|:---|:---|:---|
| **Standard Tokens / Chuẩn** | SOL, XRP, BNB, Binance, SEC, BlackRock... | `1.0×` — Không bị phạt |
| **Noise Tokens / Siêu Nhiễu** | bitcoin, btc, ethereum, eth | `0.5×` — Bị phạt chia đôi TỔNG ĐIỂM DƯƠNG bài báo, bất chấp có chứa entity chuẩn nào khác hay không. (Absolute Noise Penalty) |
| **Non-Core / TradFi** | Không có bất kỳ Core Entity nào | `0.4×` — Phạt 60% điểm rổ |

---

## 🏆 4. Thưởng Thực Thể Single-Best (Entity Bonus - V4.6)

Sau khi tính xong điểm Rổ tốt nhất, hệ thống thưởng thêm điểm phẳng cho **nhóm entity có điểm cao nhất** được phát hiện trong bài (không cộng dồn):

| Nhóm | Thưởng | Ví dụ thực thể |
|:---|:---|:---|
| `major_tokens` | **+3.0** | BTC, ETH, SOL, XRP, BNB, ADA... |
| `major_exchanges` | **+2.0** | Binance, Coinbase, Kraken, OKX... |
| `macro_entities` | **+1.0** | SEC, Fed, BlackRock, Powell, Trump... |

Ví dụ: Bài có Coinbase (exchange, +2.0) và SEC (macro, +1.0) → chỉ nhận **+2.0** (cao nhất). Nếu thêm cả Bitcoin (token, +3.0) → chỉ nhận **+3.0**.

---

## 🐋 5. Capital Flow Bonus (Dòng Tiền Cá Voi)

Nếu bài có Regex match dòng tiền thể xác:
- **Fiat:** `>= $50M` hoặc tính bằng Tỷ `$XB`
- **Crypto:** `> 100 BTC/ETH/SOL`

→ Cộng ngay **+2.0** vào `positive_score`.

---

## 🛑 6. Bộ Lọc Phạt Nặng

- **[V4.6 — Đã bỏ] Speculation Hard Reject**: Logic gán `-999.0` đã bị xóa. Các bài speculative được lọc tự nhiên qua rổ `price_analysis` (-18) + Soft Penalty (-12) + Noise Penalty (×0.5) → sẽ không vượt qua `min_publish_score = 5.0`.
- **Thầy Dùi Soft Penalty** (`-12.0`): Kích hoạt khi bài có `price_analysis` + Major Token/Exchange + **không có** Market Moving hay Negative Event.
- **Contextual Price Filter**: Nếu bài có `price_analysis` nhưng **đồng thời có** `market_moving` hoặc `macro_politics`, penalty từ rổ `price_analysis` được giảm **70%** (×0.3).

---

## 🚪 7. Ngưỡng Điểm Sàn (Min Publish Score)

`min_publish_score = 5.0` (cấu hình trong `SCORING_WEIGHTS`).

Toàn bộ bài không đạt ngưỡng này bị loại tại Phase 4 (Selector) — không được LLM xử lý, không được đăng. Nếu không bài nào qua ngưỡng → hệ thống im lặng tuyệt đối.

---

## 📊 8. Ví Dụ Chấm Điểm Toàn Diện

Minh họa 2 bài tiêu biểu đi qua toàn bộ pipeline để bóc tách rõ cách từng dòng code xử lý.

### VÍ DỤ 1: TIN TỨC CHẤT LƯỢNG CAO (The "Kitchen Sink" Good Article)

**Bài báo:** *"Coinbase launches Bitcoin ETF after SEC settlement, $500M inflow reported"*  
**Nguồn:** CoinDesk (`credibility_score=1.2`)  
**Tuổi bài:** 2 giờ | **Cluster Size:** 3 (Báo này và 2 báo khác cùng đưa tin)

```
══════════════════════════════════════════════════════════════
 1. TÍNH ĐIỂM KEYWORD (calc_keyword_score)
══════════════════════════════════════════════════════════════
 [Nhận diện Thực thể - Entity]
  - "Bitcoin"   → Thuộc major_tokens (Nhóm Token)  (+3.0) → KÍCH HOẠT NOISE PENALTY (Bất chấp mọi thứ)
  - "Coinbase"  → Thuộc major_exchanges (Nhóm Sàn) (+2.0)
  - "SEC"       → Thuộc macro_entities (Vĩ mô)     (+1.0)

 [Quy tắc Strict 1-Hit quét rổ]
  - Rổ market_moving (Cap=7.0): Khớp từ "etf" → Rổ này chốt 7.0 điểm.
  - Rổ negative_event (Cap=10.0): Khớp "settlement" → Rổ này chốt 10.0 điểm.
  - Rổ business_dev (Cap=10.0): Khớp "launches" → Rổ này chốt 10.0 điểm.
  - Rổ price_analysis (Cap=-18.0): Không khớp từ nào → 0.0

 [Lọc lấy Rổ tốt nhất - Single-Best Bucket]
  - Các rổ dương: [7.0, 10.0, 10.0] → Cao nhất là 10.0
  → best_bucket_score = +10.0

 [Cộng Thưởng Thực Thể - Single-Best Entity]
  - Các phần thưởng entity: [3.0, 2.0, 1.0] → Cấp cao nhất là Nhóm Token (+3.0)
  → best_entity_bonus = +3.0

 [Cộng Capital Flow]
  - Chứa regex "$500M" → capital_flow_bonus = +2.0

 >>> TỔNG Positive_KW = 10.0 (Rổ) + 3.0 (Thực thể) + 2.0 (Tiền) = 15.0
 >>> TỔNG Penalty_KW  = 0.0

══════════════════════════════════════════════════════════════
 2. ĐIỂM BIÊN TẬP (EDITORIAL SCORE)
══════════════════════════════════════════════════════════════
  Base Score (Dương) = 3.0
  Nội dung (Positive KW) = 15.0
  
  > Có chữ "Bitcoin" (Noise Token) -> Bị chém rụng 50% điểm dương gốc trước khi đếm Trend:
  > Base_Positive = (3.0 + 15.0) × 0.5 = 9.0
  
  Trend Bonus = (3 báo - 1) × 1.0 = +2.0 (Cộng sau chia)
  
  Biên Độ Thực = 9.0 + 2.0 = 11.0
  Nhân Uy Tín Nguồn (CoinDesk 1.2) = 11.0 × 1.2 = 13.2
  >>> Editorial_Score = 13.2

══════════════════════════════════════════════════════════════
 3. HẬU XỬ LÝ & TỔNG KẾT (FINAL SCORE)
══════════════════════════════════════════════════════════════
  Time Decay (Trễ 2h) = exp(-0.035 × 2) = 0.9324
  Topic Novelty = 1.0 (Tin chưa ai đăng)

  Final Score = 13.2 × 0.9324 × 1.0 = 12.30 điểm
  Kết quả: 12.30 >> 5.0 (Min Publish Score) → ĐƯỢC CHỌN VÀ ĐĂNG ✅
  (Dù bài báo bị xử trảm chia đôi điểm vì nhắc tên Bitcoin, nhưng nhờ có chất lượng tin tức khổng lồ từ các Bucket và Capital Flow, nó vẫn dư sức qua bài test).
```

---

### VÍ DỤ 2: BÀI OPINION / THẦY DÙI BỊ HỦY DIỆT (The Junk Article)

**Bài báo:** *"Prediction: Solana could surge to $500 next month, market sentiment is bullish"*  
**Nguồn:** CryptoPotato (`credibility_score=0.9`)  
**Tuổi bài:** 1 giờ | **Cluster Size:** 1 (Độc quyền xàm)

```
══════════════════════════════════════════════════════════════
 1. TÍNH ĐIỂM KEYWORD (calc_keyword_score)
══════════════════════════════════════════════════════════════
 [Nhận diện Thực thể - Entity]
  - "Solana" → Thuộc major_tokens (+3.0)
  (Vì Solana là Standard Token, bài này an toàn không dính phạt Noise 0.5x hay TradFi 0.4x)

 [Quy tắc Strict 1-Hit quét rổ]
  - Rổ price_analysis (Penalty: -18.0): Khớp từ "surge", "sentiment", "bullish". 
    Ngay khi quét trúng "surge", hệ thống dừng và chốt điểm rổ này là -18.0.
  - Bạn có chèn thêm 100 từ "bullish", điểm vẫn chỉ là -18.0.
  - Các rổ dương khác: Không khớp.

 [Contextual Filter & Phạt Thầy Dùi]
  - Bài này KHÔNG CÓ tin kinh tế vĩ mô (macro) hay thị trường (market_moving). Ngữ cảnh đơn thuần là đoán giá.
  - Kích hoạt luật "Soft Penalty" (-12.0) vì bài vừa phân tích giá, vừa gọi tên token lớn (để mồi chài người đọc).
  → Tổng Penalty = -18.0 (Do rổ giá) + -12.0 (Tội thầy dùi) = -30.0

 >>> TỔNG Positive_KW = 0.0 (Rổ) + 3.0 (Thực thể) + 0.0 (Tiền) = 3.0
 >>> TỔNG Penalty_KW  = -30.0

══════════════════════════════════════════════════════════════
 2. & 3. TỔNG KẾT
══════════════════════════════════════════════════════════════
  Editorial Score = (3.0 base + 3.0 kw_pos - 30.0 kw_neg + 0.0 trend) × 0.9 (Uy tín nguồn)
                  = -24.0 × 0.9 = -21.6 điểm
  
  Final Score = -21.6 × 0.9656 (Time Decay 1h) = -20.85 điểm
  Kết quả: -20.85 << 5.0 (Min Publish Score) → BỊ ĐÁ VĂNG VÀO SỌT RÁC ❌
  (Dù bài báo có gắn tên Solana để mồi click SEO, hệ thống Penalty của V4.7 bóc tách thành công nội dung sáo rỗng đoán giá và tiêu diệt triệt để)
```

---

## 🕒 9. Hao Mòn Thời Gian (Time Decay)

- **Công thức:** `exp(-0.035 × hours_passed)`
- **Ý nghĩa:** Sau ~20 giờ, điểm còn ~50%. Sau 48 giờ, còn ~18%.
- **Tính deterministic:** Tính bằng giây → không bao giờ có 2 bài có điểm bằng nhau tuyệt đối.
