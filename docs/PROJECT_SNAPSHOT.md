# PROJECT_SNAPSHOT: AI News Auto Post Bot (V3.0 Deterministic & Idempotent Architecture)

> **AI INSTRUCTION: When starting a new chat, read this file carefully. It contains the absolute source of truth for the entire system architecture, state management, scoring logic, and edge case handling.**

## 1. System Overview
A production-grade, automated bot that operates on a **Dual-Lane architecture**:
- **Express Lane (Event-Driven):** Captures breaking news from Telegram, deduplicates via macro-entity fingerprinting, processes it rapidly, and publishes it immediately.
- **RSS Lane (Interval-Driven):** Aggregates deeper macro/crypto news via RSS feeds, evaluates and ranks articles objectively using a Token-Aware Deterministic Ranking Engine, and publishes the top selections.

The system leverages LLMs (Gemini/OpenAI) to rewrite content into concise formats tailored for specific platforms, operating autonomously with robust state-driven reliability, graceful crash recovery, and extreme idempotency guards.

## 2. Global State & Idempotency Design (CRITICAL)
The system has entirely eradicated legacy JSON files. **SQLite (`data/article_state.db`) is the Absolute Single Source of Truth.**

### A. Publisher Guard (The Ultimate Idempotency Layer)
- **Table:** `published_events`
- **Purpose:** Prevents duplicate posting per platform. Every final publish attempt is tracked via an `event_fp` (e.g., `telegram:rss:12345hash`).
- **Logic:** The publisher checks this table *before* making the API call. If a post exists, it returns `success=False` and `is_duplicate=True`. The calling Lanes treat `is_duplicate=True` as a handled case, skipping the post, updating log metrics correctly (Skip instead of Success), and transitioning the article state to `POSTED` without incrementing the actual publish counter.

### B. Fingerprint Cooldown (Cross-Lane Suppression)
- **Table:** `recent_topics` 
- **Purpose:** Prevents the Bot from spamming the same event across different news sources.
- **Logic:** Express lane logs macro-entities (e.g., "Thụy Sĩ", "CPI") upon posting. RSS lane extracts fingerprints from its articles. If the RSS fingerprint exists in `recent_topics` within a 60-minute window, the RSS article receives a massive penalty (`rss_penalty_multiplier = 0.1x`) ensuring it doesn't rank high enough to be posted.

## 3. Dual-Lane Pipeline Flow

### RSS Lane (Standard Flow)
1. **Collect:** Ingests raw RSS feeds (`requests.Session` with status code validation). Parses max 20 items per feed to prevent OOM on Railway.
2. **Deduplicate:** Hard URL/GUID dedup via SQLite `rss_items` table.
3. **Rank:** Token-Aware Deterministic Ranking Engine (See Section 4).
4. **Select:** Sorts and selects the top candidates exceeding a threshold (e.g., 8.0).
5. **Summarize:** Routes to LLM to generate platform-compliant content. Uses an **Ultimate Regex Fallback Parser** to guarantee robust extraction (Headline, Summary, Impact) regardless of AI hallucination.
6. **Publish:** Pushes generated content to configured platforms based on `PLATFORM_MAPPING`. Checks the Idempotency Guard first.

### Express Lane (Breaking News Flow)
1. **Listen:** Telethon listener (`express_listener.py`) detects messages in specified Telegram channels.
2. **Hard Dedup:** Blocks exact historical duplicates (24h hash window).
3. **Keyword Filter:** Fast-pass scoring (`EXPRESS_FILTER_KEYWORDS` in `config.py`) to drop low-value chatter.
4. **Fingerprint Dedup:** Entity-level deduplication (60-minute window) to block immediate repetition.
5. **Throttle:** Configurable minimum time gap (e.g., 3 mins) between posts.
6. **Summarize & Publish:** Rapid LLM rewrite (Urgent Prompt). Checks Publisher Idempotency Guard. Skips cleanly if recognized as a duplicate retry.

## 4. The Ranking Engine (V3.0 Logic)
Located in `modules/rank.py`, configured entirely via `config.py`. It is deterministic and extremely aggressive against speculative noise.

### Core Equation
`Total Score = (Base + Editorial_Score) * Viral_Potential * Time_Decay * Source_Credibility`

### Tiered Event Prioritization & Token-Aware Logic
- **Tier 1 (Priority Events):** `priority_event` bucket (SEC actions, hacks, exchange halts). Guaranteed to skyrocket the score.
- **Tier 2 (Capital Flow Bonus):** `CAPITAL_FLOW_REGEX` detects massive fiat/crypto movements ($M/$B, ETH, BTC) adding a +4.0 bonus.
- **Contextual Filter:** If a priority/market-moving event is found alongside a price word (e.g., "BTC surges after ETF Approval"), the severe price penalty is reduced by 70%.
- **Token-Aware Buffs:** Tions of Major Tokens + Market Moving Events = +2.0 Bonus.

### The Two-Layer Speculation Filter
- **Layer 1 (Hard Reject):** Any article matching `SPECULATION_HARD_REJECT_PATTERN` (e.g., "price prediction", "price target") is immediately assigned a score of `-999.0` and dropped.
- **Layer 2 (Soft Penalty):** Words in the `price_analysis` bucket incur a heavy negative cap (e.g., -18.0). If combined with a Major Token without a valid real-world event, it incurs an *additional* `SPECULATION_SOFT_PENALTY_SCORE` (-12.0).

### Viral Potential (Momentum & Shock)
- Uses Jaccard Similarity to detect if multiple trusted sources report the same event simultaneously (Momentum).
- Calculates Shock Score based on aggressive vocabulary ("halt", "raid").

## 5. Architectural Decoupling & Future Proofing
- **Prompt Abstraction:** LLM prompts are fully decoupled in `PROMPT_TEMPLATES`. Resolved dynamically by checking `lane` ("RSS" vs "EXPRESS") and `platform`.
- **Platform Mapping:** Multi-platform routing is defined entirely in `config.py` via `PLATFORM_MAPPING` (e.g., `{"EXPRESS": ["telegram"], "RSS": ["telegram", "twitter"]}`).
- **Zero-JSON Footprint:** All state, queues, and deduplication rely strictly on `database/` SQLite files.

## 6. Key Modules Overview
- `main.py`: The async orchestrator. Handles graceful shutdown and concurrency for Both Lanes.
- `config.py`: The central nervous system for routing, ranking weights, prompts, and API keys.
- `modules/collector.py`: Network-hardened RSS fetcher (Uses Session, Timeout splitting, Status code checks).
- `modules/publisher.py`: Translates articles into REST API calls. Owns the Idempotency Guard. Contains explicit `TELEGRAM_SEND` logs for observability.
- `modules/rank.py`: Implements the V3 deterministic equation and Contextual Filters. Features a `RANK DEBUG` block in console logs for articles scoring > 8.0.
- `modules/state_manager.py`: Controls SQLite schema, migrations, WAL transactions, and sweeping mechanisms.
