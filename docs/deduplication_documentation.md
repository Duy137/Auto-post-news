# Deduplication System Documentation — V4.9

> Cập nhật: 2026-04-05 | Sửa lỗi entity_sim formula, thêm giải thích Trend Bonus.

---

## 1. Tổng Quan

Hệ thống deduplicate (`deduplicator.py`) là **Phase 2** trong pipeline RSS. Nó nhận ~100-200 bài từ collector và loại bỏ trùng lặp ở **2 cấp độ**:

1. **In-batch clustering** — gom nhóm bài trùng trong 1 lần fetch
2. **Cross-session dedup** — so sánh với bài đã thấy trong 48h qua từ DB

Đầu ra là danh sách **Lead Articles** — mỗi sự kiện chỉ có 1 đại diện duy nhất, kèm theo `cluster_size` (số bài trong cluster) để Phase 3 tính Trend Bonus.

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
  │   → Nếu sim >= 0.38: gom vào cluster, tăng cluster_size cho Lead, SKIP bài này
  │
  ├── BƯỚC 2: Cross-session dedup (nếu BƯỚC 1 không match)
  │   So sánh với recent_articles từ DB (window 48h theo published_ts)
  │   Dùng EnhancedSimilarity (threshold=0.38)
  │   → Nếu sim >= 0.38: bài đã đưa tin trong 48h → SKIP bài này
  │   ⚠️ KHÔNG tăng cluster_size (bài cũ đã qua pipeline rồi)
  │
  ├── BƯỚC 3: Narrative Continuity (nếu chưa bị SKIP)
  │   So sánh với recent_articles từ DB (window 5 ngày, threshold thấp=0.25)
  │   → Nếu match: gắn event_root_id từ sự kiện cũ (follow-up article)
  │   → Nếu không: tạo event_root_id mới
  │
  └── Thêm vào unique_articles (trở thành Lead Article, cluster_size=1)
         │
         ▼
[Phase 2 Output] unique_articles (Lead Articles, mỗi event 1 bài, kèm cluster_size)
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
entity_sim = |intersection| / max(|ents_A|, |ents_B|, 1)
```

> **Dùng `max`** (không phải `min`) — tránh trường hợp bài chỉ có 1 entity chung (bitcoin) nhưng entity_sim = 1.0 vì min(3,1)=1 → 1/1=1.0 → gom nhầm cluster quá lớn. Với max: 1/max(3,1) = 0.33 → chính xác hơn.

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

## 4. Dedup và Trend Bonus — Không Mâu Thuẫn

### 4.1 Trend Bonus là gì?

Trong Phase 3 (Ranking), `rank.py` dùng `cluster_size` để cộng **Trend Bonus** — nếu nhiều nguồn cùng đưa tin về 1 sự kiện, bài Lead được tăng điểm:

```python
# rank.py
MAX_CLUSTER_SIZE = 5
cluster_size = min(art.get("cluster_size", 1), MAX_CLUSTER_SIZE)
trend_bonus  = (cluster_size - 1) * cluster_trend_bonus   # mặc định 1.0/bài
```

Ví dụ: cluster_size = 4 → trend_bonus = +3.0 điểm.

### 4.2 Tại sao không mâu thuẫn?

Có thể nhầm tưởng Dedup "loại bỏ bài" và Trend Bonus "thưởng bài nhiều nguồn" là đối nghịch. Thực tế không phải:

**Dedup không xóa thông tin, mà chuyển thành tín hiệu:**

```
5 bài cùng sự kiện  →  Dedup gom cluster
                         ├── DROP 4 bài phụ (đúng, tránh đăng trùng)
                         └── Lead Article nhận cluster_size = 5
                                  ↓
                         Phase 3: trend_bonus = (5-1) × 1.0 = +4.0
                                  ↓
                         Lead Article ĐƯỢC BOOST nhờ cluster lớn
```

Hai cơ chế **hợp tác** chứ không chống nhau:
- Dedup loại bỏ bài trùng → đảm bảo không đăng 5 bài giống nhau
- Trend Bonus thưởng bài được nhiều nguồn đưa tin → bài quan trọng hơn leo lên top

### 4.3 Vòng đời của cluster_size (quan trọng)

`cluster_size` **không được lưu vào DB** — nó chỉ tồn tại trong RAM của 1 cycle:

```
Phase 2: tạo cluster_size trên dict article (RAM)
  ↓
Phase 3: đọc cluster_size → tính trend_bonus
  ↓
Phase 4-6: chọn bài, summarize, đăng
  ↓
Cycle kết thúc → Python garbage collector xóa → cluster_size biến mất
  ↓
Cycle mới → deduplicate_articles() chạy lại → cluster_size hoàn toàn mới
```

**Không cần logic hủy hoặc expire cluster_size** vì nó tự chết khi cycle xong.

### 4.4 Giới hạn: Trend Bonus chỉ hoạt động trong cùng 1 cycle

Nếu 5 nguồn đưa tin về cùng 1 sự kiện nhưng RSS fetch chúng ở **các cycle khác nhau**:

| Cycle | Bài | Kết quả |
|:---|:---|:---|
| Cycle 1 (7:00) | Bài A về Drift hack | A trở thành Lead, cluster_size=1, trend_bonus=0 → **POSTED** |
| Cycle 2 (9:00) | Bài B, C, D về Drift hack | Cross-session dedup bắt (sim ≥ 0.38) → **DROP hết** |

→ Bài A được đăng với trend_bonus=0, dù thực tế 4 nguồn nữa cũng đưa tin. Tín hiệu trend bị mất vì các bài đến ở khác cycle.

**Đây là đặc điểm thiết kế, không phải bug.** Trend Bonus được thiết kế để ưu tiên bài "nóng" khi nhiều nguồn ĐỒNG THỜI đưa tin trong cùng batch RSS, không phải để tích lũy qua thời gian.

---

## 5. Data Flow (State Database)

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

## 6. Tất Cả Các Lớp Chống Trùng Trong Hệ Thống

| Lớp | Phase | Cơ chế | Window | Kết quả |
|:---|:---|:---|:---|:---|
| **In-batch Clustering** | Phase 2 | EnhancedSimilarity ≥ 0.38 | Cùng batch | DROP + tăng cluster_size |
| **Cross-session Dedup** | Phase 2 | EnhancedSimilarity ≥ 0.38 | 48h | DROP (không tăng cluster_size) |
| **Fingerprint Suppression** | Phase 3 | Exact fingerprint match | 60 phút | Nhân ×0.1 điểm |
| **Entity Fatigue** | Phase 3 | Đếm entity đã POSTED | 24h | Nhân ×0.8/0.6/0.4... theo tần suất |
| **Topic Novelty Penalty** | Phase 4 | Jaccard ≥ 0.38 giữa bài đã chọn | Cùng batch | Nhân ×0.4 điểm |

---

## 7. Ví Dụ Đầy Đủ

### Ví dụ 1 — In-batch clustering + Trend Bonus ✅

```
Batch đầu vào (1 cycle):
  A: "SEC drops lawsuit against Coinbase" (CoinDesk)
  B: "U.S. Regulator Drops Charges Against Coinbase" (CryptoSlate)
  C: "SEC Coinbase case officially dismissed" (TheBlock)

Vòng lặp:
  → A: unique_articles trống → A trở thành Lead, cluster_size=1
  → B: sim(B,A) = 0.77 ≥ 0.38 → SKIP, A.cluster_size = 2
  → C: sim(C,A) = 0.72 ≥ 0.38 → SKIP, A.cluster_size = 3

Output Phase 2: [A] với cluster_size = 3

Phase 3 (Rank):
  trend_bonus = (3-1) × 1.0 = +2.0 điểm → A được boost
```

### Ví dụ 2 — Cross-session dedup: bài đến ở cycle sau → DROP ✅

```
DB (recent_articles): Bài "SEC vs Coinbase ruling" từ 20h trước (đã POSTED)

Batch hôm nay:
  C: "Court confirms SEC dismissal of Coinbase case"

→ Cross-session: sim(C, DB_article) = 0.70 ≥ 0.38
→ C bị SKIP (đã đưa tin sự kiện này trong 48h)
→ cluster_size của bài cũ KHÔNG thay đổi (đã đóng băng)
```

### Ví dụ 3 — Bài mới khác chủ đề, được giữ ✅

```
unique_articles đã có: "SEC drops lawsuit against Coinbase"

Bài mới:
  D: "Binance launches new staking product for BNB"

  ents_A = {"coinbase", "sec"}
  ents_D = {"binance", "bnb→binance"} → {"binance"}
  entity_sim = 0/max(2,1) = 0.0
  score = 0.6×0.0 + 0.4×0.0 = 0.0 < 0.38

→ D được giữ lại → trở thành Lead Article mới, cluster_size=1
```

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
  entity_sim ("david sacks" vs "david sacks", "white house" vs "white house") = 1.0
  score ≥ 0.25
  → root_id = "evt_abc123" (kế thừa từ sự kiện cũ)

→ E được giữ lại, gắn event_root_id = "evt_abc123"
```

### Ví dụ 5 — Giới hạn detection: cùng sự kiện, khác góc nhìn ⚠️

```
Cycle 1 (7:00) — POSTED:
  A: "Solana Drift's IOU Airdrop Plan Sparks Doubts After $285M Hack"

Cycle 2 (9:00) — Bài mới:
  B: "'Terrifying': Solana Founder Reacts to One of Biggest DeFi Hacks"

Cross-session check:
  ents_A = {"solana", "drift"}
  ents_B = {"solana"}
  entity_sim = 1/max(2,1) = 0.5
  
  tokens_A = {"solana", "drift", "iou", "airdrop", "plan", "sparks", "doubts", "285m", "hack"}
  tokens_B = {"terrifying", "solana", "founder", "reacts", "one", "biggest", "defi", "hacks", "history"}
  jaccard ≈ 0.07  (chỉ trùng "solana")
  
  score = 0.6×0.5 + 0.4×0.07 = 0.33 < 0.38

→ B KHÔNG bị bắt bởi dedup (dưới threshold)
→ B qua rank → đăng → 2 bài cùng vụ Drift hack xuất hiện trên channel

Nguyên nhân: 2 bài cùng sự kiện nhưng góc nhìn quá khác → entity overlap
thấp (chỉ "solana"), token overlap gần như bằng 0.
Đây là giới hạn của text-based similarity, không phải lỗi logic.
```

---

## 8. Tuning Parameters (config.py — DEDUP_CONFIG)

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

## 9. Debug Log

Khi bật `logging.DEBUG` cho module `modules.deduplicator`:

```
[DEDUP SIM] score=0.77 | entity=1.00 | jaccard=0.43 |
  title_A='SEC drops lawsuit against Coinbase' |
  title_B='U.S. Regulator Drops Charges Against Coinbase' |
  ents_A={'coinbase', 'sec'} | ents_B={'coinbase', 'sec', 'charges'}

[Event Cluster] Gom bài 'U.S. Regulator...' vào Cụm hiện tại.
Phase 2 Complete: Formed 12 Event Clusters (Lead Articles).
```
