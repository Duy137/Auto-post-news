# Deduplication System Documentation — V4.8.1

> Cập nhật: 2026-03-28 | Phản ánh trạng thái sau khi upgrade lên EnhancedSimilarity.

---

## 1. Tổng Quan

Hệ thống deduplicate (`deduplicator.py`) là **Phase 2** trong pipeline RSS. Nó nhận ~100-200 bài từ collector và loại bỏ trùng lặp ở **2 cấp độ**:

1. **In-batch clustering** — gom nhóm bài trùng trong 1 lần fetch
2. **Cross-session dedup** — so sánh với bài đã thấy trong 48h qua từ DB

Đầu ra là danh sách **Lead Articles** — mỗi sự kiện chỉ có 1 đại diện duy nhất.

---

## 2. Execution Flow

```
[Phase 1 Output] ~100-200 articles (raw từ RSS feeds)
         │
         ▼
recent_articles = get_recent_articles_for_dedup(hours=120)
  → Lấy lịch sử bài từ DB (SQLite, articles table, 5 ngày gần nhất)
         │
         ▼
for each article in collected_articles:

  ┌── BƯỚC 1: In-batch clustering
  │   So sánh với tất cả lead_articles đã accumulate trong vòng lặp này
  │   Dùng EnhancedSimilarity (threshold=0.38)
  │   → Nếu sim >= 0.38: gom vào cluster, tăng cluster_size, SKIP bài này
  │
  ├── BƯỚC 2: Cross-session dedup (nếu BƯỚC 1 không match)
  │   So sánh với recent_articles từ DB (window 48h theo published_ts)
  │   Dùng EnhancedSimilarity (threshold=0.38)
  │   → Nếu sim >= 0.38: bài đã đưa tin trong 48h → SKIP bài này
  │
  ├── BƯỚC 3: Narrative Continuity (nếu chưa bị SKIP)
  │   So sánh với recent_articles từ DB (window 5 ngày, threshold thấp=0.25)
  │   → Nếu match: gắn event_root_id từ sự kiện cũ (follow-up article)
  │   → Nếu không: tạo event_root_id mới
  │
  └── Thêm vào unique_articles (trở thành Lead Article)
         │
         ▼
[Phase 2 Output] unique_articles (Lead Articles, mỗi event 1 bài)
```

---

## 3. EnhancedSimilarity — Cơ Chế So Sánh

EnhancedSimilarity là engine chính, thay thế Jaccard thuần. Nó kết hợp 2 tín hiệu:

```
score = (0.6 × entity_similarity) + (0.4 × token_jaccard)
```

### 3.1 Entity Similarity (trọng số 0.6 — tín hiệu mạnh)

Trích xuất Named Entities từ title qua `extract_fingerprints()`:
- Static entity list: `bitcoin`, `sec`, `binance`, `trump`, `solana`...
- ALL CAPS tokens (3-8 ký tự): `ETF`, `SEC`, `FOMC`...
- CamelCase/Title Case: `David Sacks`, `White House`, `BlackRock`...

Fingerprints được **trim xuống 2 chữ đầu** để tránh CamelCase over-matching:
```
"David Sacks Wraps Up Crypto" → "david sacks"  (thay vì match nguyên cụm)
```

Fingerprints được **normalize**: `btc→bitcoin`, `eth→ethereum`, `bnb→binance`...

```
entity_sim = |intersection| / min(|ents_A|, |ents_B|, 1)
```

> Dùng `min` thay vì `max` để noise entity trong một bài không làm loãng match.

### 3.2 Token Jaccard (trọng số 0.4 — tín hiệu phụ)

Tokenize title + URL slug, bỏ stopword ngắn (≤2 chars), normalize BTC→bitcoin...

```
jaccard = |tokens_A ∩ tokens_B| / |tokens_A ∪ tokens_B|
```

### 3.3 Threshold

```
SIMILARITY_THRESHOLD = 0.38  (từ DEDUP_CONFIG trong config.py)
score >= 0.38 → cùng sự kiện → DEDUP
score <  0.38 → sự kiện khác nhau → GIỮ LẠI
```

---

## 4. Data Flow (State Database)

```
SQLite Database:
├── articles table
│   ├── id (article_id, deterministic từ canonical URL)
│   ├── canonical_url
│   ├── title
│   ├── source_name
│   ├── event_root_id      ← được deduplicator gán
│   ├── state (NEW/RANKED/SELECTED/PROCESSING/POSTED)
│   └── created_at         ← khi bot collect bài này
│
├── event_roots table
│   ├── root_id            ← "evt_abc12345" (uuid)
│   └── headline           ← title của Lead Article đầu tiên
│
└── recent_topics table    ← dùng riêng cho Fingerprint Suppression (Phase 3)
    ├── signature          ← "david sacks||white house"
    ├── source_lane        ← "RSS" hoặc "EXPRESS"
    └── created_at
```

**Luồng ghi DB trong 1 cycle:**
```
Phase 1: insert_new_article() 
  → Upsert vào articles table (UNIQUE constraint trên id, bỏ qua nếu đã tồn tại)

Phase 2 (deduplicator):
  → create_event_root(root_id, title)       → ghi event_roots
  → log_article_event_root(article_id, root_id) → update articles.event_root_id
  
Phase 3 (rank) - Fingerprint check:
  → check_recent_topic(signature, minutes=60) → query recent_topics

Phase 4 (selector) - sau khi chọn bài đăng:
  → không ghi, chỉ đọc

Phase 6 (publisher) - sau khi đăng:
  → transition_state(id, POSTED)             → update articles.state
  → insert_recent_topic(signature, "RSS")    → ghi recent_topics
```

---

## 5. Hai Cơ Chế Deduplicate Phân Biệt

| | Deduplicator (Phase 2) | Fingerprint Suppression (Phase 3) |
|:---|:---|:---|
| **Vị trí** | Trước khi rank | Trong khi rank |
| **Mục đích** | Gom bài cùng sự kiện trong batch | Phạt bài về topic vừa đăng |
| **Window** | 48h (cross-session) | 60 phút |
| **Cơ chế** | EnhancedSimilarity (0.38) | Fingerprint string match |
| **Kết quả** | Loại bỏ bài → giảm số lượng | Nhân ×0.1 → giảm điểm |

Ngoài ra, **Selector (Phase 4)** có thêm **Topic Novelty Penalty**:
```
Nếu 2 bài trong cùng batch có topic trùng → bài xếp sau × 0.4
```

---

## 6. Ví Dụ Đầy Đủ

### Ví dụ 1 — In-batch clustering: 2 bài cùng sự kiện ✅

```
Batch đầu vào:
  A: "SEC drops lawsuit against Coinbase" (CoinDesk)
  B: "U.S. Regulator Drops Charges Against Coinbase" (CryptoSlate)

Vòng lặp:
  → A: unique_articles trống → không match ai → A trở thành Lead, cluster_size=1
  → B: so sánh với A:
       ents_A = {"sec", "coinbase"}
       ents_B = {"coinbase", "charges"}   (U.S. Regulator → "us regulator" → sec qua normalize_phrase)
             → thực ra: ents_B = {"coinbase", "sec", "charges"}
       entity_sim = 2/min(2,3) = 1.0
       jaccard(tokens_A, tokens_B) ≈ 0.43
       score = 0.6×1.0 + 0.4×0.43 = 0.77 ≥ 0.38
  → B bị SKIP, A.cluster_size = 2

Output: [A] với cluster_size=2 → Trend Bonus = +1.0 trong rank
```

---

### Ví dụ 2 — Cross-session dedup: tin đã đưa 20h trước ✅

```
DB (recent_articles): Bài "SEC vs Coinbase ruling" từ 20h trước

Batch hôm nay:
  C: "Court confirms SEC dismissal of Coinbase case"

Vòng lặp:
  → C: so sánh với unique_articles (trống) → không match
  → Cross-session: so sánh với DB article "SEC vs Coinbase ruling":
       entity_sim: {"coinbase", "sec"} vs {"coinbase", "court", "sec"} = 1.0
       score = 0.6×1.0 + 0.4×jaccard ≈ 0.7 ≥ 0.38
  → C bị SKIP (đã đưa tin sự kiện này trong 48h qua)
```

---

### Ví dụ 3 — Bài mới khác chủ đề, được giữ ✅

```
unique_articles đã có: "SEC drops lawsuit against Coinbase"

Bài mới:
  D: "Binance launches new staking product for BNB"

So sánh:
  ents_A = {"coinbase", "sec"}
  ents_D = {"binance", "bnb→binance"}  → {"binance"}
  entity_sim = 0/min(2,1) = 0.0
  jaccard("sec drops lawsuit coinbase", "binance launches staking bnb") ≈ 0.0
  score = 0.6×0.0 + 0.4×0.0 = 0.0 < 0.38

→ D được giữ lại → trở thành Lead Article mới
```

---

### Ví dụ 4 — Narrative Continuity: follow-up article ✅

```
DB (recent_articles, 3 ngày trước):
  "David Sacks appointed as White House crypto czar"
  → event_root_id = "evt_abc123"

Batch hôm nay:
  E: "David Sacks steps down from White House crypto role"

BƯỚC 1: Không match bài nào trong batch hiện tại
BƯỚC 2: Cross-session (48h window): "3 ngày" vượt quá 48h → không xét
BƯỚC 3: Narrative Continuity (5 ngày, threshold 0.25):
  ents giữa E và DB article:
  entity_sim ("david sacks" vs "david sacks", "white house" vs "white house") = 1.0
  score = 0.6×1.0 + ... ≥ 0.25
  → root_id = "evt_abc123" (kế thừa từ sự kiện cũ)

→ E được giữ lại, gắn event_root_id = "evt_abc123"
  (Thể hiện đây là tin tiếp theo của cùng câu chuyện David Sacks)
```

---

### Ví dụ 5 — False positive được xử lý đúng ✅

```
Hai bài về entity khác nhau nhưng dùng từ giống:
  F: "Binance launches new product"
  G: "Coinbase launches new product"

  ents_F = {"binance"}
  ents_G = {"coinbase"}
  entity_sim = 0/min(1,1) = 0.0
  jaccard = {"launches", "new", "product"}/union ≈ 0.60

  score = 0.6×0.0 + 0.4×0.60 = 0.24 < 0.38

→ G được giữ lại (không bị nhầm là duplicate của F) ✅
```

---

## 7. Tuning Parameters (config.py — DEDUP_CONFIG)

```python
DEDUP_CONFIG = {
    "entity_weight": 0.6,        # Tăng → entity match quan trọng hơn
    "token_weight": 0.4,         # Giảm khi tăng entity_weight
    "similarity_threshold": 0.38, # Tăng → strict hơn, ít dedup hơn

    "normalization_phrases": {   # "us regulator" → "sec" (TRƯỚC tokenize)
        "us regulator": "sec",
        "u.s. regulator": "sec",
        "federal reserve": "fed",
        "united states": "usa",
    },
    "normalization_tokens": {    # BTC → bitcoin (SAU tokenize)
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "xrp": "ripple",
        "bnb": "binance",
    },
}
```

**Hướng dẫn tune:**
- `threshold` tăng (0.45+) → bắt ít trùng hơn, bài gần giống vẫn lọt qua
- `threshold` giảm (0.30-) → bắt nhiều hơn nhưng risk false positive
- `entity_weight` tăng (0.7+) → chỉ dedup khi cùng entity, token giống nhau không đủ
- Thêm vào `normalization_phrases` → cải thiện match cho các cụm từ đồng nghĩa

---

## 8. Debug Log

Khi bật `logging.DEBUG` cho module `modules.deduplicator`:

```
[DEDUP SIM] score=0.77 | entity=1.00 | jaccard=0.43 |
  title_A='SEC drops lawsuit against Coinbase' |
  title_B='U.S. Regulator Drops Charges Against Coinbase' |
  ents_A={'coinbase', 'sec'} | ents_B={'coinbase', 'sec', 'charges'}

[Event Cluster] Gom bài 'U.S. Regulator...' vào Cụm hiện tại.
Phase 2 Complete: Formed 12 Event Clusters (Lead Articles).
```
