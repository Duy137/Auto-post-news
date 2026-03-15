# PROJECT_SNAPSHOT: AI News Auto Post Bot (V2.2 Tiered & Hardened Architecture)

## 1. System Overview
A production-grade, automated bot that operates on a Dual-Lane architecture, refined for high-impact signal detection and network resilience.

## 2. Lane Pipeline Flow
### RSS Lane (Standard)
- **Collect:** Uses `requests.Session` for persistent TCP connections. Limits ingestion to 20 items/source to prevent overhead.
- **Deduplicate:** SQLite-backed idempotency.
- **Rank:** Deterministic Tiered Ranking Engine (V4.0).
  - **Tier 1 (Priority Events):** Explicit support for SEC actions, Hacks, and Exchange halts with high scoring weights.
  - **Tier 2 (Capital Flow):** Bonus points (+4.0) for large fund movements detected via advanced regex.
  - **Tier 3 (Token-Aware):** Context-aware awards/penalties for major assets.
  - **Contextual Filter:** Mitigates speculation penalties by 70% if the news also matches a priority event keyword (e.g., "Surges after ETF Approval").
  - **Two-Layer Filter:** Hard-rejects blatant predictions (-999.0) while applying soft penalties (-18.0) to price movement commentary.
- **Publish:** Explicit Telegram send logs for total observability.
- **Select:** Sorts and selects the top candidates.
- **Summarize:** Routes to LLM to generate platform-compliant content. Uses an **Ultimate Regex Fallback Parser** to guarantee robust extraction (Headline, Summary, Impact, Hashtags) regardless of AI hallucination or custom separators.
- **Publish:** Pushes generated content to configured platforms (e.g., Twitter, Telegram, Facebook) with lane-specific formatting rules (e.g., preserving hyperlinks only for RSS, omitting HASHTAGS on Telegram to keep the channel clean).

### Express Lane (Breaking News)
- **Listen:** Telegram listener detects messages in specified channels.
- **Hard Dedup:** Blocks exact historical duplicates (24h hash window).
- **Keyword Filter:** Fast-pass scoring to drop low-value chatter.
- **Fingerprint Dedup:** Entity-level deduplication (60-minute window) using Proper Nouns and Macro-Economics Static Entities (e.g., "Thụy Sĩ", "Unemployment", "Israel") to prevent spamming the same event across different news sources.
- **Throttle:** Configurable minimum time gap (e.g., 3 mins) between posts.
- **Summarize & Publish:** Rapid LLM rewrite and instant publishing with delayed retry mechanisms. Output format strips source links and uses alert emojis (`🚨`).

## 3. Production Hardening Features
- **Network Resilience:** Implemented `requests.Session` with split timeouts `(3.05, 10)` and HTTP status validation to prevent parsing 4xx/5xx error pages.
- **Idempotency Accuracy:** Metrics now distinguish between successful `POSTED` events and `SKIPPED (Duplicate)` events.
- **Observability:** Centralized `📊 [RANK DEBUG]` logging provides a complete breakdown of why an article was selected or rejected.

## 4. State & Idempotency Design
- **SQLite (`data/article_state.db`):** The *Absolute Single Source of Truth* for the entire project. All legacy JSON footprint (`posted_tweets.json`, `seen_articles.json`) has been completely eradicated.
- **Fingerprinting (`recent_topics`):** Shared across both lanes. Express lane outputs lock fingerprints for 60 minutes. RSS lane verifies against this table to suppress older duplicate articles (Cooldown Suppression Hook).
- **Publisher Guard:** Idempotency tracking embedded cleanly inside SQLite (`published_events`) to prevent duplicate API posting per platform, even during retry logic. `PlatformResult` now includes an `is_duplicate` flag to ensure accurate metrics.

## 5. Key Modules
- `main.py`: The async orchestrator governing the concurrent execution of the Express Listener and the RSS polling loop.
- `express_listener.py`: The event-driven Telegram hook. Resolves bound `loop` AsyncIO contexts gracefully.
- `express_filter.py & express_fingerprint.py`: Handle rapid deduplication natively via hardcoded macro-entity lexicons.
- `state_manager.py`: Controls SQLite schema, WAL transactions, automated database sweeping, and fingerprint/cooldown state logic.
- `rank.py`: The deterministic intelligence scoring module providing absolute transparency via point breakdowns.
- `summarize.py`: Resolves dynamic prompts, routes requests to LLMs (OpenAI/Gemini) with automatic rate-limit backing off, and guarantees structural integrity via extreme regex fallbacks.
- `publisher.py`: Translates verified articles into REST API calls for mapped platforms via a unified engine, distinguishing physical formats between `RSS` and `EXPRESS` lanes.
- `config.py`: The central nervous system containing all global variables, toggle flags, API Keys, Platform Mappings, Prompt Templates, and zero-JSON file path setups.

## 6. Current Operational Status
- **Phase 10 Completed:** The Dual-Lane V2.1 Architecture is structurally sealed, feature-complete, rigorously decoupled, and 100% JSON-independent.
- **Phase 11 (Market-Moving Scoring) Completed:** Integrated Token-Aware modifiers to correctly identify and prioritize high-value market drivers over speculative analysis.
- **Future Ready:** Capable of scaling entirely new Lanes or Platforms by solely injecting them into the `PLATFORM_MAPPING` and `PROMPT_TEMPLATES` config engine without tearing down core executors.
