# PROJECT_SNAPSHOT: AI News Auto Post Bot (V4.5 Entity-Aware Architecture)

> **AI INSTRUCTION: When starting a new chat, read this file carefully. It contains the absolute source of truth for the entire system architecture, state management, scoring logic, and edge case handling.**

## 1. System Overview
A production-grade, automated bot that operates on a **Dual-Lane architecture**:
- **Express Lane (Event-Driven):** Captures breaking news from Telegram, deduplicates via macro-entity fingerprinting (10-min window), processes it rapidly, and publishes immediately.
- **RSS Lane (Interval-Driven):** Aggregates crypto/macro news via RSS feeds, evaluates and ranks articles using the V4.5 Entity-Aware Deterministic Ranking Engine, and publishes only articles that exceed `min_publish_score = 5.0`.

LLM Provider: **Gemini** (primary) with Gemma fallback. Content is rewritten in Vietnamese.

## 2. Global State & Idempotency Design (CRITICAL)
**SQLite (`data/article_state.db`) is the Absolute Single Source of Truth.** No JSON files.

### A. Publisher Guard (Ultimate Idempotency Layer)
- **Table:** `published_events`
- **Logic:** Publisher checks this table *before* the API call. If `event_fp` exists, returns `is_duplicate=True` and skips. The article is marked `POSTED` without incrementing the publish counter.

### B. Fingerprint Cooldown (Cross-Lane Suppression)
- **Table:** `recent_topics`
- **Window:** `fingerprint_window_minutes = 10` (default, configurable)
- **Logic:** Express lane logs fingerprints on publish. RSS lane applies `rss_penalty_multiplier = 0.1×` to articles matching a recent topic fingerprint within the window.

## 3. Dual-Lane Pipeline Flow

### RSS Lane
1. **Collect** → `modules/collector.py` — Network-hardened RSS fetcher (max 20 items/feed)
2. **Deduplicate** → Hard URL/GUID dedup via `rss_items` SQLite table
3. **Rank** → V4.5 Deterministic Ranking Engine (`modules/rank.py`)
4. **Select** → Filters articles with `score >= min_publish_score (5.0)`, then picks top candidates (`modules/selector.py`)
5. **Summarize** → Gemini (Flash → Gemma fallback, 30s timeout, 500 max_tokens) rewrites in Vietnamese bullet format
6. **Publish** → Pushes to platforms in `PLATFORM_MAPPING["RSS"]`. Checks Idempotency Guard first.

### Express Lane
1. **Listen** → Telethon listener detects `🔴` messages in source Telegram channel
2. **Hard Dedup** → 24h hash window blocks exact message repeats
3. **Keyword Filter** → `EXPRESS_FILTER_KEYWORDS` score threshold (min 15.0)
4. **Fingerprint Dedup** → 10-minute entity-level window
5. **Throttle** → Min 3-minute gap between consecutive posts
6. **Summarize & Publish** → Gemma (30s timeout), compact 1-2 sentence format with IMPACT field

## 4. The Ranking Engine (V4.5 Entity-Aware Logic)

Full detail in `docs/ranking_engine_documentation.md`. Summary:

### Core Formula
```
Total Score = (Editorial_Score + Entity_Bonus + Trend_Bonus + Capital_Flow_Bonus)
              × Source_Multiplier × Time_Decay × Topic_Novelty_Penalty
```

### Keyword Buckets
| Bucket | Cap | Key Behavior |
|:---|:---|:---|
| `market_moving` | +10.0 | Discrete event signals only. Penalty-immune. |
| `macro_politics` | +10.0 | Macro/geopolitics. Penalty-immune. |
| `business_development` | +10.0 | Subject to Asset Tiering penalty |
| `negative_event` | +10.0 | Subject to Asset Tiering penalty |
| `major_tech` | +8.0 | Subject to Asset Tiering penalty |
| `price_analysis` | -18.0 | Penalty bucket. Reduces score. |

### Asset Tiering Penalty (V4.4)
Applied to bucket scores of `business_development`, `negative_event`, `major_tech`:
- **Standard Tokens** (SOL, XRP, Binance, SEC...): `1.0×` — No penalty
- **Noise Tokens** (bitcoin, BTC, ethereum, ETH): `0.5×` — 50% penalty on bucket scores
- **Non-Core/TradFi**: `0.4×` — 60% penalty

**V4.5 Fix — Unconditional Noise Penalty:** After all entity bonuses are summed, if the article ONLY has Noise Tokens (no Standard Tokens), the full `positive_score` is multiplied by `noise_penalty_multiplier (0.5)`. This prevents Entity Bonus (+3) from inflating scores for purely Bitcoin-labeled opinion columns.

### Entity Bonuses (V4.5)
Independent flat bonuses added after bucket scoring, before Source Multiplier:
- `major_tokens` present → **+3.0**
- `major_exchanges` present → **+2.0**
- `macro_entities` present → **+1.0**

### Min Publish Score (V4.5)
`min_publish_score = 5.0` — Hard cutoff at Selector phase. Silent if no articles qualify.

### Speculation Guards
- **Hard Reject**: `price prediction`, `price target`, `forecast $X` → `-999.0` score, instantly dropped
- **Soft Penalty**: `price_analysis` bucket score (-18.0) + Soft Penalty (-10.0) for token+speculation combo

## 5. LLM Configuration

```python
"lane_models": {
    "RSS":     ["gemini-2.5-flash", "gemma-3-27b-it"],  # Flash first, Gemma fallback
    "EXPRESS": ["gemma-3-27b-it"]                        # Fixed, fast model
}
"lane_timeouts": { "RSS": 30, "EXPRESS": 30 }
"max_tokens": 500
"temperature": 0.3
```

Key rotation is implemented at the inner loop level. Model fallback happens when all keys for the current model are exhausted or return FATAL_ERROR (timeout/504).

## 6. Platform Routing

```python
PLATFORM_MAPPING = {
    "EXPRESS": ["telegram"],
    "RSS":     ["telegram"]   # Add "twitter" to enable Twitter posting for RSS
}
```

Twitter `dry_run = True` by default in `TWITTER_CONFIG`. Set to `False` only after verifying dry-run output.

## 7. Key Modules
- `main.py` — Async orchestrator, graceful shutdown, dual-lane concurrency
- `config.py` — Central config: RSS sources, scoring weights, prompt templates, API keys
- `modules/rank.py` — V4.5 ranking equation, entity bonuses, noise penalty
- `modules/selector.py` — Min score filter + topic novelty dedup (Phase 4)
- `modules/summarize.py` — LLM call with key rotation + model fallback
- `modules/publisher.py` — Multi-platform posting with idempotency guard
- `modules/express_listener.py` — Telethon-based breaking news listener
- `modules/express_fingerprint.py` — Entity extraction for Express dedup
- `modules/state_manager.py` — SQLite schema, WAL transactions, maintenance sweeps
