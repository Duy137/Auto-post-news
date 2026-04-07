# Ranking Engine Documentation — V5.1

> Cập nhật: 2026-04-07 | Đồng bộ 100% với code `pipeline/rank.py` hiện tại.  
> Thay đổi chính: Entity Fatigue V5.1 (extract_fingerprints), keyword_caps updated, Speculation Soft Penalty documented.

---

## 1. Tổng Quan

Hệ thống chấm điểm (`pipeline/rank.py`) là **Phase 3** trong Content Pipeline. Nó nhận danh sách Lead Articles từ Deduplicator (Phase 2) và gán điểm cho từng bài để Selector (Phase 4) có thể chọn bài tốt nhất đưa vào `publish_queue`.

**Công thức tổng quát:**

```
base_positive               = (Base + Positive_KW_Score) × Noise_Multiplier
Editorial_Score             = (base_positive + Penalty_KW + Trend_Bonus) × Source_Credibility
total_score                 = Editorial_Score × Time_Decay
total_score                *= Entity_Fatigue_Mult          (nếu < 1.0)
total_score                *= Topic_Novelty_Mult           (nếu < 1.0)

Trong đó:
  Positive_KW_Score = best_bucket_score + entity_bonus + capital_flow_bonus
  Penalty_KW        = penalty_score (rổ âm price_analysis) + speculation_soft_penalty
```

> **Lưu ý quan trọng:** `Positive_KW_Score` đã bao gồm cả Entity Bonus và Capital Flow Bonus — chúng được cộng vào `positive_kw_score` trước khi truyền ra ngoài. Noise Penalty nhân lên toàn bộ `base_score + positive_kw_score`.

---

## 2. Execution Flow (từng bước)

```
[Phase 2 Output] List[Article] (unique Lead Articles, kèm cluster_size)
         │
         ▼
── PRE-LOOP: Entity Fatigue Counting ──────────────────────
   posted_titles = get_posted_titles_24h()
     → Lấy title bài state='POSTED' trong 24h từ bảng articles (CHỈ RSS, không có Express)
   Với MỖI posted title:
     extract_fingerprints(title) → list entities
     → Đếm tần suất: entity_post_count = {"sec": 3, "bitcoin": 2, "powell": 1, ...}
   Log top 10 entity xuất hiện nhiều nhất
         │
         ▼
for each article:
  ├── A. calc_keyword_score(title, summary)
  │      → positive_kw_score    (best_bucket + entity_bonus + capital_flow)
  │      → penalty_kw_score     (rổ âm: price_analysis + speculation_soft_penalty)
  │      → token_modifier       (speculation soft penalty value, để log)
  │      → has_negative_event   (bool)
  │      → has_noise_core       (bool)
  │
  ├── B. Capital Flow Regex scan (title + summary)
  │      → Nếu match: capital_flow_bonus = +2.0, cộng vào positive_kw_score
  │
  ├── C. Source Credibility lookup
  │      → src_cred = SOURCE_CREDIBILITY[source_name] (default 1.0)
  │
  ├── D. Cluster Trend Bonus
  │      → cluster_size = min(art.cluster_size, 5)     ← CAP tối đa 5
  │      → trend_bonus = (cluster_size - 1) × 1.0
  │
  ├── E. Noise Penalty (nếu has_noise_core = True)
  │      → base_positive = (base_score + positive_kw_score) × 0.5
  │      → Nếu không noise: base_positive = base_score + positive_kw_score
  │
  ├── F. Editorial Score
  │      → editorial = (base_positive + penalty_kw_score + trend_bonus) × src_cred
  │
  ├── G. Time Decay
  │      → decay = max(exp(-0.035 × hours_passed), 0.12)
  │      → total_score = editorial × decay
  │
  ├── H. Entity Fatigue (V5.1)
  │      → Trích fingerprints từ title bài hiện tại
  │      → Với mỗi fingerprint: lấy count từ entity_post_count
  │      → mult = max(1.0 - count × 0.2, 0.0)
  │      → Lấy mult THẤP NHẤT (entity bị phạt nhiều nhất quyết định)
  │      → total_score *= entity_fatigue_mult
  │
  ├── I. Topic Novelty (Fingerprint Suppression)
  │      → signature = join fingerprints bằng "||"
  │      → check_recent_topic(signature, minutes=60)
  │      → Nếu match: total_score *= 0.1 (phạt 90%)
  │
  └── J. Final Score
         → art["score"] = total_score (đã qua tất cả multiplier)
         │
         ▼
── POST-LOOP ──────────────────────────────────────────────
   Lọc bỏ bài score < -500 (legacy hard reject guard)
   Sort DESC theo score
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
Đây là "điểm sàn tối thiểu" để bài không có keyword nào vẫn có thể tồn tại. Một bài chỉ có base_score (3.0) sẽ luôn bị loại vì dưới `min_publish_score = 5.0`.

---

### 3.2 Keyword Scoring — Nguyên tắc Scan

> **[V4.8 FIX]** Chỉ scan **TITLE** — không scan summary.  
> Lý do: summary do phóng viên tóm tắt, thường dùng từ mạnh (launch, partner...) khiến bài PR/hội nghị vô danh leo lên đầu oan.

**Nguyên tắc Single-Best Bucket + Strict 1-Hit:**
- Mỗi rổ keyword: chỉ cần **1 từ khóa** khớp → nhận trọn 100% điểm cap của rổ
- Chỉ lấy **rổ dương có điểm cao nhất** (`best_bucket_score = max(...)`)
- Các rổ âm (penalty) cộng dồn vào `penalty_score` độc lập

**Bảng các rổ (keyword_caps trong config.py):**

| Rổ | Cap | Miễn Asset Penalty? | Ghi chú |
|:---|:---:|:---:|:---|
| `market_moving` | **+4.0** | ✅ Miễn | Sự kiện thị trường: ETF approval, halving, legal tender |
| `macro_politics` | **+5.0** | ✅ Miễn | Chính trị/vĩ mô: SEC, Fed, legislation, CPI, rate |
| `business_development` | **+8.0** | ❌ Bị phạt | Kinh doanh: funding, launch, partnership, acquisition |
| `negative_event` | **+8.0** | ❌ Bị phạt | Tiêu cực: hack, exploit, lawsuit, outage, ban |
| `major_tech` | **+3.0** | ❌ Bị phạt | Công nghệ: mainnet, protocol, network, hard fork |
| `price_analysis` | **-18.0** | — | Rổ phạt: price, rally, bullish, analyst says, RSI |

**Ví dụ keyword tiêu biểu:**
- `market_moving`: `etf approval`, `halving`, `buys bitcoin`, `institutional inflow`, `cbdc launch`
- `macro_politics`: `sec`, `fed`, `legislation`, `cpi`, `rate`, `white house`, `senate`, `congress`, `powell`, `fomc`, `inflation`, `treasury`, `bill`, `regulator`
- `business_development`: `funding`, `launch`, `partnership`, `acquisition`, `raises`, `buyback`, `token burn`, `staking launch`, `merger`
- `negative_event`: `hack`, `exploit`, `lawsuit`, `outage`, `ban`, `arrest`, `scam`, `breach`, `delist`, `token unlock`, `freeze funds`, `settlement`
- `major_tech`: `mainnet`, `protocol`, `network`, `roadmap`, `hard fork`, `soft fork`
- `price_analysis`: `price`, `rally`, `bullish`, `targets`, `analyst says`, `RSI`, `MACD`, `resistance`, `support`, `breakout`, `correction`, `pump`, `dump`, `surge`, `drop`, `plunge`, `could hit`, `set to`, `poised to`, `toward $`, `what to expect`, `happens next`

**Chi tiết cách scan:**

```python
# Pseudo-code
text = title.lower()    # CHỈ TITLE, lowercase
best_bucket_score = 0.0
penalty_score = 0.0

for category, cap in keyword_caps.items():
    for keyword in keyword_categories[category]:
        if re.search(r"\b" + keyword + r"\b", text):
            matched = True
            break   # ← Strict 1-Hit: 1 keyword = full cap

    if matched:
        if cap > 0:
            score = cap
            # Asset Tiering (xem 3.3)
            if category not in ["market_moving", "macro_politics"]:
                if not has_core_entity:
                    score *= 0.3    # Non-core penalty
            best_bucket_score = max(best_bucket_score, score)
        else:
            penalty_score += cap    # Rổ âm cộng dồn
```

---

### 3.3 Asset Tiering — Non-Core Entity Penalty

Đây là hệ thống phân hạng tài sản để phạt bài về coin vô danh/TradFi không liên quan.

**Cách detect entity (title-only, dùng word boundary `\b`):**

```python
# Core Entity = Standard Tokens + Macro Entities + Major Exchanges
# (KHÔNG bao gồm Noise Tokens)
standard_core_list = standard_tokens + macro_entities + major_exchanges

has_standard_core = detect_entities(title, standard_core_list)
has_noise_core    = detect_entities(title, noise_tokens)
has_core_entity   = has_standard_core or has_noise_core
```

**Phân loại Core Entity:**

| Loại | Danh sách config | Ví dụ | Điểm thưởng Entity Bonus |
|:---|:---|:---|:---:|
| Noise Token | `noise_tokens` | bitcoin, btc, ethereum, eth | — (bị Noise Penalty, xem 3.4) |
| Standard Token | `major_tokens` (loại trừ noise) | SOL, XRP, BNB, AVAX, DOGE, ADA, LINK, UNI, SUI... | **+3.0** |
| Major Exchange | `major_exchanges` | Binance, Coinbase, OKX, Kraken, Bybit, KuCoin... | **+2.0** |
| Macro Entity | `macro_entities` | Trump, BlackRock, Fidelity, MicroStrategy, Saylor, Musk, Vitalik, Tether, USDT, USDC, Circle, FOMC, Powell | **+1.0** |

**Entity Bonus:** Chỉ lấy bonus **cao nhất** (single-best), không cộng dồn.

```python
# Pseudo-code
entity_bonus_candidates = []
if title có major_tokens:   entity_bonus_candidates.append(3.0)
if title có major_exchanges: entity_bonus_candidates.append(2.0)
if title có macro_entities:  entity_bonus_candidates.append(1.0)
entity_bonus = max(entity_bonus_candidates) if any else 0.0
positive_kw_score += entity_bonus
```

**Non-Core Penalty:** Nếu `has_core_entity = False` (không tìm thấy BẤT KỲ entity nào — kể cả noise):
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
→ base_positive = (Base + Positive_KW) × 0.5
```

Penalty này áp lên toàn bộ điểm dương (gồm base_score + best_bucket + entity_bonus + capital_flow) **TRƯỚC KHI** cộng Penalty_KW và Trend_Bonus.

> **Lưu ý:** Noise penalty chia đôi điểm dương, nhưng `penalty_kw_score` (giá trị âm) và `trend_bonus` (giá trị dương) được cộng **SAU** khi chia noise. Công thức:
>
> `editorial = (base_positive_after_noise + penalty_kw + trend_bonus) × src_cred`

```
Ví dụ:
"Bitcoin hits $100k (price analysis)"
→ base=3, best_bucket=0 (price_analysis là rổ âm), entity_bonus=3.0 (bitcoin ∈ major_tokens)
→ positive_kw = 0 (bucket) + 3.0 (entity) = 3.0
→ noise=True → base_positive = (3+3) × 0.5 = 3.0
→ penalty = -18.0 (price_analysis)
→ editorial = (3.0 - 18.0) × 1.1 = -16.5 → score âm → BỊ LOẠI
```

---

### 3.5 Speculation Soft Penalty

Ngoài rổ `price_analysis` (-18.0), có thêm một lớp phạt kép cho bài "thầy dùi" — bài nhắc đến token/sàn cụ thể + từ khóa phân tích giá:

```python
if has_price_analysis and not (has_market_moving or has_negative_event):
    if title chứa major_tokens hoặc major_exchanges:
        penalty_score += SPECULATION_SOFT_PENALTY_SCORE  # -12.0
```

**Điều kiện kích hoạt:**
1. Bài khớp rổ `price_analysis`
2. Bài **KHÔNG** đồng thời khớp `market_moving` hoặc `negative_event` (context filter)
3. Title chứa tên token/sàn cụ thể (SOL, Binance, XRP...)

**Kết quả:** `penalty_score = -18.0 (bucket) + (-12.0) (soft penalty) = -30.0`

```
Ví dụ:
"Solana could reach $500 next month, analyst predicts"
→ "analyst predicts" → price_analysis → penalty = -18.0
→ SOL ∈ major_tokens → speculation soft penalty = -12.0
→ positive_kw = 0 (bucket dương tốt nhất = 0) + 3.0 (entity bonus SOL) = 3.0
→ base_positive = 3 + 3 = 6.0 (no noise)
→ editorial = (6.0 - 30.0) × 1.1 = -26.4 → BỊ LOẠI NẶNG
```

---

### 3.6 Capital Flow Bonus

Pattern regex (chỉ bắt tiền lớn ≥ $50M):

```regex
\$?(?:(?:[5-9][0-9]|[1-9][0-9]{2,})\s*(?:million|m)|[0-9]+(?:\.[0-9]+)?\s*(?:billion|trillion|b|t))
|\b[1-9][0-9]{2,}\s*(?:BTC|ETH|SOL)\b
```

Ví dụ match: `$500M`, `$2B`, `$1.5 billion`, `100 BTC`, `1 trillion`

```
Nếu title HOẶC summary chứa capital flow pattern → +2.0 điểm
```

> **Note:** Capital flow scan dùng cả **title + summary** (khác với keyword scan chỉ title-only). Lý do: con số tiền thường nằm ở summary.

---

### 3.7 Source Credibility

Mỗi nguồn RSS có `credibility_score` riêng trong config:

| Nguồn | Credibility |
|:---|:---:|
| CoinDesk, Bitcoin Magazine, TechCrunch | 1.1 |
| CryptoSlate, BeInCrypto | 1.0-1.05 |
| Nguồn không xác định | 1.0 (mặc định) |

Nhân trực tiếp vào Editorial Score.

---

### 3.8 Cluster Trend Bonus

```python
MAX_CLUSTER_SIZE = 5   # ← CAP cứng, tránh cluster_size=37 gây trend_bonus=+36
cluster_size = min(art.cluster_size, MAX_CLUSTER_SIZE)
trend_bonus = (cluster_size - 1) × 1.0
```

Nếu 3 tờ báo cùng đưa tin → `cluster_size = 3` → `trend_bonus = +2.0`  
Nếu 10 tờ báo cùng đưa tin → `cluster_size = min(10, 5) = 5` → `trend_bonus = +4.0` (bị cap)

> Trend bonus cộng **SAU KHI** đã nhân Noise Penalty, để tránh khuếch đại bài nhiễu.  
> `editorial = (base_positive + penalty + trend_bonus) × src_cred`

**Vòng đời cluster_size:** Chỉ tồn tại trong RAM của 1 cycle. Cycle mới → deduplicate lại → cluster_size hoàn toàn mới ← Không lưu DB.

---

### 3.9 Time Decay

**[V4.8 FINAL]** Chỉ dùng `published_ts` (ngày RSS đăng bài). `root_created_ts` không tham gia decay.

```python
MIN_VALID_TS = 1577836800    # 2020-01-01
effective_ts = published_ts if published_ts >= MIN_VALID_TS else current_ts
hours_passed = (current_ts - effective_ts) / 3600
decay = max(exp(-0.035 × hours_passed), 0.12)  # floor = 0.12
```

> **Fallback:** Nếu `published_ts` = 0 hoặc trước 2020 → dùng `current_ts` → decay = 1.0 (không phạt tuổi). Đảm bảo bài không có timestamp không bị giết oan.

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

### 3.10 Entity Fatigue (V5.1 — MỞ RỘNG)

**Mục đích:** Phạt bài khi entity đã xuất hiện nhiều lần trong 24h qua, tránh đăng liên tục về cùng 1 chủ đề/nhân vật.

**Trước V5.1:** Chỉ check ~30 entity cố định từ config (major_tokens + major_exchanges + macro_entities).

**Sau V5.1:** Dùng `extract_fingerprints()` (file `express/fingerprint.py`) để detect **MỌI entity** — bao gồm:
- Static entities (~80 entries): `binance`, `sec`, `trump`, `bitcoin`, `ftx`...
- $TOKEN format: `$BTC`, `$SOL`...
- ALL CAPS (3-8 ký tự, loại trừ common words): `ETF`, `FOMC`, `SEC`...
- CamelCase/Title Case (≥2 từ viết hoa liên tiếp): `David Sacks`, `White House`, `Black Rock`...

**Tính entity_fatigue_mult:**

```python
# PRE-LOOP: đếm entity từ bài đã POSTED trong 24h (CHỈ RSS, không có Express)
entity_post_count = {}
for title in get_posted_titles_24h():
    for fp in extract_fingerprints(title):
        entity_post_count[fp] += 1

# PER-ARTICLE: lấy entity bị phạt nhiều nhất
entity_fatigue_mult = 1.0
for fp in extract_fingerprints(article_title):
    count = entity_post_count.get(fp, 0)
    if count >= 1:
        mult = max(1.0 - count * 0.2, 0.0)    # Giảm tuyến tính
        entity_fatigue_mult = min(entity_fatigue_mult, mult)  # Lấy thấp nhất

total_score *= entity_fatigue_mult
```

| Số lần entity đã POSTED trong 24h | Hệ số Entity Fatigue |
|:---:|:---:|
| 0 | 1.0 (không phạt) |
| 1 | 0.8 |
| 2 | 0.6 |
| 3 | 0.4 |
| 4 | 0.2 |
| 5+ | **0.0** (triệt tiêu hoàn toàn) |

> **Quan trọng:** Entity Fatigue lấy entity bị phạt **NHIỀU NHẤT** (mult thấp nhất) để quyết định. Ví dụ bài có entity `sec` (count=2, mult=0.6) và `coinbase` (count=0, mult=1.0) → dùng 0.6.

> **Cross-lane:** Chỉ đếm bài RSS POSTED (bảng `articles` WHERE state='POSTED'). Express lane ghi vào bảng `express_seen` riêng → **KHÔNG ảnh hưởng** Entity Fatigue của RSS.

---

### 3.11 Topic Novelty Multiplier (Fingerprint Suppression)

Đây là lớp bảo vệ **cross-lane** — nếu Express hoặc RSS vừa đăng 1 bài về topic X, thì bài RSS tiếp theo về topic X trong 60 phút sẽ bị phạt cực nặng.

```python
fingerprints = extract_fingerprints(title)
signature = "||".join(fingerprints)   # VD: "coinbase||sec"
window = ORCHESTRATION_CONFIG["fingerprint_window_minutes"]  # default 60

if check_recent_topic(signature, minutes=window):
    topic_novelty_multiplier = 0.1    # Phạt 90%
    total_score *= 0.1
```

> **Khác biệt với Entity Fatigue:** 
> - Entity Fatigue đếm _tần suất_ entity qua 24h, phạt dần dần (0.8 → 0.6 → ...).
> - Topic Novelty check _exact signature match_ trong 60 phút gần nhất, phạt ngay 90%.
> - Cả hai có thể áp dụng **đồng thời** trên cùng 1 bài.

---

### 3.12 Min Publish Score (Phase 4 — Selector)

```python
min_publish_score = 5.0
```

Selector (`pipeline/selector.py`) loại bỏ mọi bài có `final_score < 5.0` **trước khi** chọn top N. Nếu tất cả bài dưới ngưỡng → return `[]` → pipeline không queue bài nào.

**Ngoài ra, Selector còn có Phase 4 Diversity Check:**
- Nếu nhiều bài cùng topic đều vượt 5.0, Selector so sánh Jaccard similarity giữa chúng.
- Bài trùng topic với bài đã chọn trước bị nhân `topic_novelty_penalty = 0.4` (phạt 60%) rồi đẩy lại pool re-rank.
- Đảm bảo output luôn đa dạng chủ đề.

---

## 4. Ví Dụ Chấm Điểm Chi Tiết

### Ví dụ 1 — Bài tốt, lên đầu ✅

**Title:** `"SEC drops lawsuit against Coinbase"`  
**Published:** 2h trước

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `sec` → macro_politics → exempt penalty | best_bucket = +5.0 |
| Entity | Coinbase ∈ major_exchanges | entity_bonus = +2.0 |
| Noise check | không có BTC/ETH | ×1.0 |
| positive_kw | 5.0 (bucket) + 2.0 (entity) | 7.0 |
| base_positive | (3.0 + 7.0) × 1.0 | 10.0 |
| Penalty | không có price_analysis | 0.0 |
| Trend | cluster=1 | +0.0 |
| Editorial | (10.0 + 0 + 0) × 1.1 | 11.0 |
| Decay | exp(-0.035×2) | 0.932 |
| Entity Fatigue | sec posted 0x | ×1.0 |
| **Final** | 11.0 × 0.932 × 1.0 | **10.25** |
| Kết quả | ≥ 5.0 → **ĐƯỢC ĐĂNG** | ✅ |

---

### Ví dụ 2 — Bài phân tích giá + token = bị phạt kép ❌

**Title:** `"Solana could reach $500 next month, analyst predicts"`

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `analyst predicts` → price_analysis | penalty_bucket = -18.0 |
| Best bucket dương | Không có rổ dương nào khớp | 0.0 |
| Entity | SOL ∈ major_tokens (standard, non-noise) | entity_bonus = +3.0 |
| Speculation Soft | price_analysis + có token + không có market_moving/negative | -12.0 |
| Noise check | SOL không phải noise token | ×1.0 |
| positive_kw | 0.0 (bucket) + 3.0 (entity) | 3.0 |
| base_positive | (3.0 + 3.0) × 1.0 | 6.0 |
| Total penalty | -18.0 + (-12.0) | -30.0 |
| Editorial | (6.0 - 30.0 + 0) × 1.1 | -26.4 |
| **Final** | ≈ -26.4 | **-26.4** |
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
| Keyword Scan | `hacked` → negative_event | best_bucket = +8.0 |
| Entity | Binance ∈ major_exchanges | entity_bonus = +2.0 |
| Capital Flow | `$1.5B` match regex | +2.0 |
| Noise check | không có btc/eth | ×1.0 |
| positive_kw | 8.0 + 2.0 + 2.0 | 12.0 |
| base_positive | (3 + 12) × 1.0 | 15.0 |
| Penalty | không có price_analysis | 0.0 |
| Editorial | 15.0 × 1.1 | 16.5 |
| Decay | exp(-0.035×0.5) | 0.983 |
| **Final** | 16.5 × 0.983 | **16.22** |
| Kết quả | ≥ 5.0 → **ĐƯỢC ĐĂNG** | ✅ |

---

### Ví dụ 5 — Bài cũ 3 ngày, bị loại vì decay floor ❌

**Title:** `"Bitfinex hacker Ilya Lichtenstein credits Trump for early release"`  
**Published:** 72h trước (RSS feed vẫn giữ)

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | "hacker" ≠ "hack" (word boundary) → không match negative_event | 0.0 |
| Entity | Trump ∈ macro_entities | entity_bonus = +1.0 |
| positive_kw | 0.0 + 1.0 | 1.0 |
| base_positive | 3 + 1 | 4.0 |
| Editorial | 4.0 × 1.1 | 4.4 |
| Decay | 72h > 60h → floor | **0.12** |
| **Final** | 4.4 × 0.12 | **0.53** |
| Kết quả | < 5.0 → **BỊ LOẠI** | ❌ |

---

### Ví dụ 6 — Entity Fatigue triệt tiêu bài lặp ❌

**Giả sử:** Trong 24h đã POSTED 3 bài về SEC.

**Title:** `"SEC Commissioner Calls for Clearer Rules"`

| Bước | Tính toán | Kết quả |
|:---|:---|:---:|
| Keyword Scan | `sec` → macro_politics | best_bucket = +5.0 |
| Entity | Không entity nào trong bonus lists khớp "Commissioner" | 0.0 |
| base_positive | 3 + 5 | 8.0 |
| Editorial | 8.0 × 1.0 | 8.0 |
| Decay | 1h trước | 0.966 |
| Score trước fatigue | 8.0 × 0.966 | 7.73 |
| Entity Fatigue | `sec` đã POSTED 3 lần → mult = max(1.0-3×0.2, 0) = **0.4** | ×0.4 |
| **Final** | 7.73 × 0.4 | **3.09** |
| Kết quả | < 5.0 → **BỊ LOẠI** | ❌ |

---

## 5. Debug Log Format

```
📊 [RANK DEBUG] Article: 'SEC drops lawsuit against Coinbase...'
  [+] Base: 3.0 | Source Cred: 1.1 | Trend Bonus: +0.0 (Cluster: 1)
  [+] Kw Bonus: 7.00 | Capital Flow: +0.0 | Token Mod: +0.0
  [-] Penalty: 0.00
  [*] Mults: Noise=1.0x | TimeDecay=0.93 | EntityFatigue=1.0x
  => FINAL_SCORE    : 10.25

😴 [ENTITY FATIGUE] 'SEC Commissioner Calls for Cl...' — entity 'sec' posted 3x → ×0.4
```

**Đọc log:**
- `Kw Bonus` = best_bucket_score + entity_bonus (SAU khi non-core penalty, TRƯỚC khi noise). **KHÔNG bao gồm Capital Flow** (Capital Flow hiển thị riêng).
- `Token Mod` = Speculation Soft Penalty value (0 nếu không kích hoạt, -12.0 nếu bài thầy dùi)
- `Penalty` = tổng penalty_kw_score (price_analysis + soft penalty)
- `Noise=0.5x` = bài có noise token, tất cả điểm dương bị chia đôi
- `TimeDecay=0.12` = bài cũ hơn 60h, đang ở floor
- `EntityFatigue=0.4x` = entity phổ biến nhất đã posted 3 lần
- `FINAL_SCORE < 5.0` → bài sẽ bị Selector loại trước khi vào queue
- Bài có `FINAL_SCORE >= 5.0` hoặc `has_negative_event=True` → log ở mức INFO
- Bài thấp điểm → log ở mức DEBUG (không hiện trên console production)

---

## 6. Các Tham Số Tune được (config.py)

```python
SCORING_WEIGHTS = {
    "base_score": 3.0,
    "time_decay_lambda_per_hour": 0.035,   # Tăng → decay nhanh hơn
    "cluster_trend_bonus": 1.0,            # Tăng → ưu tiên trend mạnh hơn
    "non_core_penalty_multiplier": 0.3,    # Tăng → phạt nhẹ hơn với coin vô danh
    "noise_penalty_multiplier": 0.5,       # Giảm → phạt nặng hơn bài BTC/ETH thuần
    "min_publish_score": 5.0,              # Tăng → ngưỡng cao hơn, chọn lọc hơn
    "SPECULATION_SOFT_PENALTY_SCORE": -12.0,  # Phạt kép bài thầy dùi (cộng thêm vào -18 price_analysis)
    "CAPITAL_FLOW_BONUS": 2.0,             # Thưởng bài có dòng vốn lớn
    "entity_bonuses": {
        "major_tokens": 3.0,               # Bài nhắc SOL, XRP, BNB...
        "major_exchanges": 2.0,            # Bài nhắc Binance, Coinbase...
        "macro_entities": 1.0              # Bài nhắc Trump, BlackRock, FOMC...
    },
    "keyword_caps": {
        "market_moving": 4.0,              # ETF approval, halving
        "macro_politics": 5.0,             # SEC, Fed, legislation
        "business_development": 8.0,       # Funding, launch, M&A
        "negative_event": 8.0,             # Hack, exploit, lawsuit
        "major_tech": 3.0,                 # Mainnet, protocol
        "price_analysis": -18.0            # Rổ phạt: giảm điểm bài phân tích giá
    },
    "topic_novelty_penalty": 0.4           # Selector diversity penalty (Phase 4)
}
```

### Tham số bên ngoài SCORING_WEIGHTS:

```python
ORCHESTRATION_CONFIG = {
    "fingerprint_window_minutes": 60,      # Topic Novelty check window
    "rss_penalty_multiplier": 0.1,         # Phạt 90% nếu topic trùng trong window
}
```

---

## 7. Tóm Tắt Thứ Tự Tính Toán

```
1. calc_keyword_score(title) → cho ra:
   ├── positive_kw_score = best_bucket + entity_bonus
   └── penalty_kw_score  = price_analysis + soft_penalty

2. Capital Flow scan (title+summary) → cộng vào positive_kw_score

3. base_positive = (base_score + positive_kw_score)
   if noise: base_positive *= 0.5

4. editorial = (base_positive + penalty_kw + trend_bonus) × src_cred

5. total = editorial × time_decay

6. if entity_fatigue < 1.0: total *= entity_fatigue

7. if topic_novelty < 1.0: total *= 0.1

8. Ghi vào art["score"] → chuyển Phase 4
```
