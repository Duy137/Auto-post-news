# PROJECT_SNAPSHOT: AI News Auto Post Bot (V2.1 Pure SQLite & Deterministic Architecture)

## 1. System Overview
A production-grade, automated bot that operates on a Dual-Lane architecture:
- **Express Lane (Event-Driven):** Captures breaking news from Telegram, processes it rapidly, and publishes it immediately.
- **RSS Lane (Interval-Driven):** Aggregates deeper macro/crypto news via RSS feeds, evaluates and ranks articles objectively, and publishes the top selections.

The system leverages LLMs (Gemini/OpenAI) to rewrite content into concise, engaging formats tailored for specific platforms, operating autonomously with state-driven reliability and graceful crash recovery.

## 2. Dual-Lane Pipeline Flow
### RSS Lane (Standard)
- **Collect:** Ingests raw RSS feeds normalized into standard `Article` objects.
- **Deduplicate:** Hard and Soft deduplication via SQLite mapping, entirely eliminating legacy JSON history.
- **Rank:** Deterministic Anti-Price Speculation Engine. Utilizes tier-based Regex patterns, strict Keyword Score Caps, and soft penalties mapped exclusively to macro and tech events (Zero-LLM Topic Classification).
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

## 3. Future-Proof Routing Architecture
- **Prompt Abstraction Layer:** LLM prompts are fully decoupled. Prompts are resolved dynamically based on `lane` and `platform` configuration via `PROMPT_TEMPLATES`, allowing distinct writing styles (e.g., urgent for Express, neutral for RSS).
- **Config-Driven Platform Mapping:** The `PLATFORM_MAPPING` dictionary globally dictates which lane is allowed to publish to which platform. Listeners are entirely decoupled from publishing destinations.

## 4. State & Idempotency Design
- **SQLite (`data/article_state.db`):** The *Absolute Single Source of Truth* for the entire project. All legacy JSON footprint (`posted_tweets.json`, `seen_articles.json`) has been completely eradicated.
- **Fingerprinting (`recent_topics`):** Shared across both lanes. Express lane outputs lock fingerprints for 60 minutes. RSS lane verifies against this table to suppress older duplicate articles (Cooldown Suppression Hook).
- **Publisher Guard:** Idempotency tracking embedded cleanly inside SQLite (`published_events`) to prevent duplicate API posting per platform, even during retry logic. Includes automated vacuum/maintenance.

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
- **Future Ready:** Capable of scaling entirely new Lanes or Platforms by solely injecting them into the `PLATFORM_MAPPING` and `PROMPT_TEMPLATES` config engine without tearing down core executors.
