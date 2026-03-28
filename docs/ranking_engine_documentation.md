# Ranking Engine Documentation — V4.8.1

> Cập nhật: 2026-03-28 | Phản ánh trạng thái code hiện tại sau session fix bugs.

---

## 1. Tổng Quan

Hệ thống chấm điểm (`rank.py`) là **Phase 3** trong pipeline RSS. Nó nhận danh sách Lead Articles từ Deduplicator và gán điểm cho từng bài để Selector có thể chọn bài tốt nhất.

**Công thức tổng quát:**

```
Noise_Adjusted_Positive = (Base + Keyword_Bucket + Entity_Bonus + Capital_Flow) × Noise_Multiplier
Editorial_Score         = (Noise_Adjusted_Positive + Penalty_KW + Trend_Bonus) × Source_Credibility
Final_Score             = Editorial_Score × Time_Decay × Topic_Novelty_Multiplier
```

---

## 2. Execution Flow (từng bước)

```
[Phase 2 Output] List[Article] (unique Lead Articles)
         │
         ▼
for each article:
  ├── A. calc_keyword_score(title)            → positive_kw, penalty_kw, token_mod, has_negative_event, has_noise_core
  ├── B. Capital Flow Regex scan (title+summary) → capital_flow_bonus
  ├── C. Source Credibility lookup            → src_cred
  ├── D. Cluster Trend Bonus                 → trend_bonus
  ├── E. Noise Penalty (nếu noise token)     → base_positive × 0.5
  ├── F. Editorial Score                     → (base_positive + penalty + trend) × src_cred
  ├── G. Time Decay                          → exp(-0.035 × hours_since_published)
  ├── H. Topic Novelty (Fingerprint check)   → ×0.1 nếu topic trùng trong 60 phút
  └── I. Final Score                         → editorial × decay × novelty
         │
         ▼
[Phase 3 Output] List[Article] có trường "score" và "score_detail"
```

---

## 3. Chi Tiết Từng Thành Phần

### 3.1 Base Score
```
Cố định = 3.0 cho mọi bài
```
Đây là "điểm sàn tối thiểu" để bài không có keyword nào vẫn có thể tồn tại.

---

### 3.2 Keyword Scoring — Nguyên tắc Scan

> **[V4.8 FIX]** Chỉ scan **TITLE** — không scan summary.  
> Lý do: summary do phóng viên tóm tắt, thường dùng từ mạnh (launch, partner...) khiến bài PR/hội nghị vô danh leo lên đầu oan.

**Nguyên tắc Single-Best Bucket + Strict 1-Hit:**
- Mỗi rổ keyword: chỉ cần **1 từ khóa** khớp → nhận trọn 100% điểm cap của rổ
- Chỉ lấy **rổ có điểm cao nhất** (`best_bucket_score = max(...)`)
- Các rổ âm (penalty) cộng dồn vào `penalty_score` độc lập

**Bảng các rổ:**

| Rổ | Cap | Miễn Asset Penalty? |
|:---|:---:|:---:|
| `market_moving` | +4.0 | ✅ Miễn |
| `macro_politics` | +5.0 | ✅ Miễn |
| `business_development` | +10.0 | ❌ Bị phạt |
| `negative_event` | +10.0 | ❌ Bị phạt |
| `major_tech` | +3.0 | ❌ Bị phạt |
| `price_analysis` | **-18.0** | — |

**Ví dụ keyword tiêu biểu:**
- `market_moving`: `etf approval`, `halving`, `buys bitcoin`, `institutional inflow`
- `macro_politics`: `sec`, `fed`, `legislation`, `cpi`, `rate`, `white house`, `senate`
- `business_development`: `funding`, `launch`, `partnership`, `acquisition`, `raises`
- `negative_event`: `hack`, `exploit`, `lawsuit`, `arrested`, `scam`, `ban`
- `major_tech`: `mainnet`, `protocol`, `network`, `roadmap`, `hard fork`
- `price_analysis`: `price`, `rally`, `bullish`, `targets`, `analyst says`, `RSI`

---

### 3.3 Asset Tiering — Non-Core Entity Penalty

Đây là hệ thống phân hạng tài sản để phạt bài về coin vô danh/TradFi không liên quan.

**Phân loại Core Entity:**

| Loại | Ví dụ | Điểm thưởng Entity Bonus |
|:---|:---|:---:|
| Noise Token | bitcoin, btc, ethereum, eth | — (xem 3.4) |
| Standard Token | SOL, XRP, BNB, AVAX, DOGE... | +3.0 |
| Major Exchange | Binance, Coinbase, OKX, Kraken... | +2.0 |
| Macro Entity | Trump, BlackRock, Fed, Tether, USDT... | +1.0 |

**Entity Bonus:** Chỉ lấy bonus cao nhất (single-best), không cộng dồn.

**Non-Core Penalty:** Nếu không tìm thấy bất kỳ Core Entity nào:
- Bucket `business_development`, `negative_event`, `major_tech` bị nhân `× 0.3` (giữ 30%)
- Bucket `market_moving`, `macro_politics` **miễn phạt** (tin vĩ mô không cần entity)

```
Ví dụ:
"Zoomex at EthCC: Focus on Infrastructure and Trading"
→ Zoomex: không có trong bất kỳ entity list nào
→ EthCC: \b eth \b không match "ethcc" → no noise token
→ has_core_entity = False
→ major_tech bucket (nếu khớp) × 0.3 = 0.9
→ Thực tế: "infrastructure", "trading" không nằm trong bất kỳ bucket → Kw=0
→ Final ≈ 3.0 × 1.1 × 0.9 ≈ 2.97 → DƯỚI ngưỡng 5.0 → BỊ LOẠI
```

---

### 3.4 Absolute Noise Penalty

`noise_tokens = ["bitcoin", "btc", "ethereum", "eth"]`

Khi bài nhắc đến Bitcoin/ETH nhưng không có sự kiện thực chất (chỉ dùng tên để câu view):

```
has_noise_core = True
→ (Base + Positive_KW) × 0.5
```

Penalty này áp lên toàn bộ điểm dương **TRƯỚC KHI** cộng Penalty_KW và Trend_Bonus.

```
Ví dụ:
"Bitcoin hits $100k (price analysis)"
→ base=3, negative_event=0, price_analysis=-18, noise=True
→ base_positive = (3+0) × 0.5 = 1.5
→ editorial = (1.5 - 18) × 1.1 = -18.15 → score âm → BỊ LOẠI
```

---

### 3.5 Capital Flow Bonus

Pattern: `$500M`, `$2B`, `100 BTC`, `1 trillion`...

```
Nếu title hoặc summary chứa capital flow pattern → +2.0 điểm
```

> Note: Capital flow scan dùng cả **title + summary** (khác với keyword scan chỉ title-only). Lý do: con số tiền thường nằm ở summary.

---

### 3.6 Source Credibility

Mỗi nguồn RSS có `credibility_score` riêng trong config:

| Nguồn | Credibility |
|:---|:---:|
| CoinDesk, Bitcoin Magazine, TechCrunch | 1.1 |
| CryptoSlate, BeInCrypto | 1.0-1.05 |
| Nguồn không xác định | 1.0 (mặc định) |

---

### 3.7 Cluster Trend Bonus

```
trend_bonus = (cluster_size - 1) × 1.0
```

Nếu 3 tờ báo cùng đưa tin → `cluster_size = 3` → `trend_bonus = +2.0`

> Trend bonus cộng **SAU KHI** đã nhân Noise Penalty, để tránh khuếch đại bài nhiễu.

---

### 3.8 Time Decay

**[V4.8 FINAL]** Chỉ dùng `published_ts` (ngày RSS đăng bài). `root_created_ts` không tham gia decay.

```python
effective_ts = published_ts if published_ts >= 2020-01-01 else current_ts
hours_passed = (current_ts - effective_ts) / 3600
decay = max(exp(-0.035 × hours_passed), 0.12)  # floor = 0.12
```

| Tuổi bài | Decay |
|:---|:---:|
| Vừa đăng (0h) | 1.000 |
| 6h trước | 0.808 |
| 12h trước | 0.653 |
| 24h trước | 0.430 |
| 48h trước | 0.186 |
| Rất cũ (>60h) | **0.12 (floor)** |

**Lý do có floor 0.12:** Một số RSS feed giữ bài cũ 3-5 ngày trong top 20. Nếu không có floor, các bài này sẽ score ≈ 0 và gây noise trong pipeline. Với floor 0.12, ngay cả bài editorial_score cao nhất (~22) cũng chỉ đạt: `22 × 0.12 = 2.64 < 5.0 (threshold)` → bị loại tự động.

---

### 3.9 Topic Novelty Multiplier (Fingerprint Suppression)

Trước khi finalize score, hệ thống kiểm tra DB xem topic này có được đăng trong **60 phút qua** không:

```
fingerprints = extract_fingerprints(title)  # entity names, ALL CAPS tokens, CamelCase
signature = "david sacks||white house"
check_recent_topic(signature, minutes=60)
  → True  → topic_novelty_multiplier = 0.1  (phạt 90%)
  → False → topic_novelty_multiplier = 1.0  (bình thường)

final_score = editorial_score × decay × topic_novelty_multiplier
```

---

### 3.10 Min Publish Score

```
min_publish_score = 5.0
```

Selector loại bỏ mọi bài có `final_score < 5.0` trước khi chọn top N.

---

## 4. Ví Dụ Chấm Điểm Chi Tiết

### Ví dụ 1 — Bài tốt, lên đầu ✅

**Title:** `"SEC drops lawsuit against Coinbase"`  
**Published:** 2h trước

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `sec` → macro_politics → exempt | +5.0 |
| Entity | Coinbase ∈ major_exchanges | +2.0 |
| Noise check | không có BTC/ETH | ×1.0 |
| base_positive | (3 + 5 + 2) | 10.0 |
| Penalty | không có price_analysis | 0.0 |
| Trend | cluster=1 | +0.0 |
| Editorial | 10.0 × 1.1 | 11.0 |
| Decay | exp(-0.035×2) | 0.932 |
| **Final** | 11.0 × 0.932 | **10.25** |
| Kết quả | ≥ 5.0 → **ĐƯỢC ĐĂNG** | ✅ |

---

### Ví dụ 2 — Bài phân tích giá, bị loại ❌

**Title:** `"Bitcoin could hit $150k says analyst"`

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `analyst says` → price_analysis | -18.0 |
| Entity | BTC → noise token | `has_noise_core=True` |
| Noise | base(3) + best_bucket(0) = 3 × 0.5 | 1.5 |
| Penalty | -18.0 | -18.0 |
| Editorial | (1.5 - 18) × 1.1 | -18.15 |
| **Final** | ≈ -18.15 | **-18.15** |
| Kết quả | < 5.0 → **BỊ LOẠI** | ❌ |

---

### Ví dụ 3 — Bài PR hội nghị vô danh, bị loại ❌

**Title:** `"Zoomex to Attend EthCC Cannes, Focusing on Industry Dialogue"`

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | không khớp keyword nào trong title | 0.0 |
| Entity | Zoomex không có, EthCC không trigger \beth\b | `has_core_entity=False` |
| Noise | không có noise token | ×1.0 |
| base_positive | 3 + 0 = 3 | 3.0 |
| Editorial | 3.0 × 1.1 | 3.3 |
| Decay | exp(-0.035×1) | 0.966 |
| **Final** | 3.3 × 0.966 | **3.19** |
| Kết quả | < 5.0 → **BỊ LOẠI** | ❌ |

---

### Ví dụ 4 — Bài hack exchange lớn ✅

**Title:** `"Binance hacked for $1.5B in stablecoin exploit"`

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `hacked`, `exploit` → negative_event | +10.0 |
| Entity | Binance ∈ major_exchanges | +2.0 |
| Capital Flow | `$1.5B` match regex | +2.0 |
| Noise check | không có btc/eth | ×1.0 |
| base_positive | 3 + 10 + 2 + 2 | 17.0 |
| Editorial | 17.0 × 1.1 | 18.7 |
| Decay | exp(-0.035×0.5) | 0.983 |
| **Final** | 18.7 × 0.983 | **18.38** |
| Kết quả | ≥ 5.0 → **ĐƯỢC ĐĂNG** | ✅ |

---

### Ví dụ 5 — Bài cũ 3 ngày, bị loại vì decay floor ❌

**Title:** `"Bitfinex hacker Ilya Lichtenstein credits Trump for early release"`  
**Published:** 72h trước (RSS feed vẫn giữ)

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `hack` trong title → negative_event... wait, "hacker" không phải "hack" | 0.0 |
| Entity | Trump ∈ macro_entities | +1.0 |
| base_positive | 3 + 0 + 1 | 4.0 |
| Editorial | 4.0 × 1.1 | 4.4 |
| Decay | 72h > 60h → floor | **0.12** |
| **Final** | 4.4 × 0.12 | **0.53** |
| Kết quả | < 5.0 → **BỊ LOẠI** | ❌ |

---

## 5. Debug Log Format

```
📊 [RANK DEBUG] Article: 'SEC drops lawsuit against Coinbase...'
  [+] Base: 3.0 | Source Cred: 1.1 | Trend Bonus: +0.0 (Cluster: 1)
  [+] Kw Bonus: 7.00 | Capital Flow: +0.0 | Token Mod: +0.0
  [-] Penalty: 0.00
  [*] Mults: Noise=1.0x | TimeDecay=0.93
  => FINAL_SCORE    : 10.25
```

**Đọc log:**
- `Kw Bonus` = best_bucket_score + entity_bonus (SAU khi non-core penalty, TRƯỚC khi noise)
- `Noise=0.5x` = bài có noise token, tất cả điểm dương bị chia đôi
- `TimeDecay=0.12` = bài cũ hơn 60h, đang ở floor
- `FINAL_SCORE < 5.0` → bài sẽ bị Selector loại trước khi publish

---

## 6. Các Tham Số Tune được (config.py)

```python
SCORING_WEIGHTS = {
    "base_score": 3.0,
    "time_decay_lambda_per_hour": 0.035,   # Tăng → decay nhanh hơn
    "cluster_trend_bonus": 1.0,            # Tăng → ưu tiên trend mạnh hơn
    "non_core_penalty_multiplier": 0.3,    # Giảm → phạt nhẹ hơn với coin vô danh
    "noise_penalty_multiplier": 0.5,       # Giảm → phạt nặng hơn bài BTC/ETH thuần
    "min_publish_score": 5.0,              # Tăng → ngưỡng cao hơn, chọn lọc hơn
    "entity_bonuses": {
        "major_tokens": 3.0,
        "major_exchanges": 2.0,
        "macro_entities": 1.0
    },
    "keyword_caps": {
        "market_moving": 4.0,
        "macro_politics": 5.0,
        "business_development": 10.0,
        "negative_event": 10.0,
        "major_tech": 3.0,
        "price_analysis": -18.0
    }
}
```
