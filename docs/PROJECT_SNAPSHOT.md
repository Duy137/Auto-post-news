# PROJECT_SNAPSHOT: AI News Auto Post Bot (V5.1 — Per-Platform Timer Architecture)

> **AI INSTRUCTION: When starting a new chat, read this file carefully. It contains the absolute source of truth for the entire system architecture, state management, scoring logic, and edge case handling.**

## 1. System Overview
A production-grade, automated bot that operates on a **Dual-Lane architecture** with a **decoupled pipeline**:
- **Content Pipeline (Async Task 1):** Quét RSS → Dedup → Rank → Select → Summarize → Lưu vào `publish_queue` (kho bài). KHÔNG đăng bài trực tiếp.
- **Platform Publisher (Async Task 2):** Mỗi vài phút check timing rule từng platform (gap / scheduled / interval). Nếu đến giờ → lấy bài tốt nhất từ kho → đăng lên platform đó.
- **Express Lane (Async Task 3, Event-Driven):** Captures breaking news từ Telegram → dedup → summarize → đăng ngay lập tức.

LLM Provider: **Gemini** (primary) with Gemma fallback. Content is rewritten in Vietnamese.

## 2. Module Structure (V5.0)

```
Auto post news/
├── main.py                          ← Async orchestrator (3 tasks)
├── config.py                        ← Central config + hot-reload
├── models.py                        ← TypedDict definitions
├── modules/
│   ├── __init__.py
│   ├── state_manager.py             ← SQLite DB, queue CRUD, maintenance
│   ├── pipeline/                    ← RSS Pipeline Core
│   │   ├── collector.py             ← RSS fetcher (network-hardened)
│   │   ├── deduplicator.py          ← In-batch clustering + cross-session dedup
│   │   ├── rank.py                  ← V5.1 Ranking Engine (Entity Fatigue mở rộng)
│   │   ├── selector.py              ← Min score filter + topic novelty
│   │   └── summarize.py             ← LLM call with key rotation + model fallback
│   ├── express/                     ← Express Lane
│   │   ├── listener.py              ← Telethon-based breaking news listener
│   │   ├── filter.py                ← Keyword score filter
│   │   └── fingerprint.py           ← Entity extraction (proper nouns, $TOKEN, CAPS)
│   └── publishing/                  ← Per-Platform Publisher
│       ├── publisher.py             ← Multi-platform posting with idempotency guard
│       ├── timing.py                ← Per-platform timing logic (gap/scheduled/interval)
│       └── telethon_client.py       ← Shared Telethon singleton
```

## 3. Global State & Idempotency Design (CRITICAL)
**SQLite (`data/article_state.db`) is the Absolute Single Source of Truth.** No JSON files.

### A. Publisher Guard (Ultimate Idempotency Layer)
- **Table:** `published_events`
- **Logic:** Publisher checks this table *before* the API call. If `event_fp` exists for platform, returns `is_duplicate=True` and skips.

### B. Fingerprint Cooldown (Cross-Lane Suppression)
- **Table:** `recent_topics`
- **Window:** `fingerprint_window_minutes = 60` (default, configurable)
- **Logic:** Express lane logs fingerprints on publish. RSS lane applies `rss_penalty_multiplier = 0.1×` to articles matching a recent topic fingerprint within the window.

### C. Publish Queue (V5.0 — Per-Platform)
- **Table:** `publish_queue` — bài đã summarize, pre-formatted cho từng platform
- **Table:** `platform_publish_log` — log thời gian đăng mỗi platform (cho timing check)

## 4. Pipeline Flow

### Content Pipeline (Task 1) — Chạy mỗi 30 phút (configurable)
1. **Collect** → `pipeline/collector.py` — Network-hardened RSS fetcher (max 20 items/feed)
2. **Deduplicate** → EnhancedSimilarity (entity 0.6 + token 0.4, threshold 0.38)
3. **Rank** → V5.1 Ranking Engine với Entity Fatigue mở rộng
4. **Select** → Filters articles with `score >= min_publish_score (5.0)`, top 1
5. **Summarize** → LLM rewrite in Vietnamese + Polish step (Gemma, temp=0)
6. **Queue** → `build_content()` format cho 3 platform → `insert_to_publish_queue()`

### Platform Publisher (Task 2) — Check mỗi 5 phút (configurable)
1. **Check Timing** → `timing.should_publish_now(platform)` — async, per-platform
2. **Pick Best** → `pick_best_from_queue(platform)` — bài READY, chưa expired, chưa đăng platform này, adjusted_score cao nhất
3. **Publish** → `publish_single_from_queue()` → idempotency check → API call → mark published

### Express Lane (Task 3) — Event-Driven
1. **Listen** → Telethon listener detects `🔴` messages in source Telegram channel
2. **Hard Dedup** → 24h hash window blocks exact message repeats
3. **Keyword Filter** → `EXPRESS_FILTER_KEYWORDS` score threshold (min 15.0)
4. **Fingerprint Dedup** → configurable window (default 60 min)
5. **Throttle** → Min 3-minute gap between consecutive posts
6. **Summarize & Publish** → LLM rewrite → publish immediately

## 5. Per-Platform Timing Modes (V5.0)

| Mode | Mô tả | Config Keys |
|:---|:---|:---|
| `gap` | Check khoảng cách bài cuối trên channel. Telegram dùng Telethon API, fallback DB | `min_gap_hours`, `gap_channel_id` |
| `scheduled` | Đăng đúng giờ cố định (±5 phút tolerance) | `schedule` (list "HH:MM") |
| `interval` | Cách đều N giờ kể từ lần đăng trước | `interval_hours` |

Mỗi platform config riêng trong `ORCHESTRATION_CONFIG["platform_timing"]`.

## 6. Ranking Engine (V5.1)

### Core Formula
```
Noise_Adjusted_Positive = (Base + Keyword_Bucket + Capital_Flow) × Noise_Multiplier
Editorial_Score         = (Noise_Adjusted_Positive + Penalty_KW + Trend_Bonus) × Source_Credibility
Final_Score             = Editorial_Score × Time_Decay × Topic_Novelty × Entity_Fatigue
```

### Entity Fatigue (V5.1 — Mở rộng)
Dùng `extract_fingerprints()` để detect MỌI entity trong title bài đã POSTED 24h.
Phạt tuyến tính: lần 1=1.0, lần 2=0.8, lần 3=0.6, lần 4=0.4, lần 5=0.2, lần 6+=0.0.

### Keyword Bucket Caps
| Bucket | Cap | Miễn Asset Penalty? |
|:---|:---:|:---:|
| `market_moving` | +4.0 | ✅ |
| `macro_politics` | +5.0 | ✅ |
| `business_development` | +8.0 | ❌ |
| `negative_event` | +8.0 | ❌ |
| `major_tech` | +3.0 | ❌ |
| `price_analysis` | -18.0 | — |

## 7. LLM Configuration

```python
"lane_models": {
    "RSS":     ["gemini-2.5-flash", "gemma-3-27b-it"],
    "EXPRESS": ["gemma-3-27b-it"]
}
"lane_timeouts": { "RSS": 30, "EXPRESS": 30 }
"max_tokens": 500
"temperature": 0.3
```

## 8. Platform Routing

```python
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS":     ["telegram"]   # Add "twitter", "facebook" to enable
}
```

## 9. Environment Variables (New in V5.0)

| Variable | Default | Mô tả |
|:---|:---|:---|
| `CONTENT_PIPELINE_INTERVAL` | 30 | Phút — Content Pipeline quét RSS |
| `PUBLISH_CHECK_INTERVAL` | 5 | Phút — Publisher check timing |
| `QUEUE_MAX_AGE_HOURS` | 6 | Giờ — Bài quá cũ bị expired |
| `TG_PUBLISH_MODE` | gap | Timing mode cho Telegram |
| `TG_MIN_GAP_HOURS` | 4 | Khoảng cách tối thiểu (gap mode) |
| `TG_GAP_CHANNEL_ID` | — | Channel ID để Telethon check bài cuối |
| `TW_PUBLISH_MODE` | scheduled | Timing mode cho Twitter |
| `TW_SCHEDULE` | 07:00,...,00:00 | Khung giờ đăng Twitter |
| `FB_PUBLISH_MODE` | interval | Timing mode cho Facebook |
