# PROJECT_SNAPSHOT: AI News Auto Post Bot (V2 Dual-Lane Architecture)

## 1. System Overview
A production-grade, automated bot that operates on a Dual-Lane architecture:
- **Express Lane (Event-Driven):** Captures breaking news from Telegram, processes it rapidly, and publishes it immediately.
- **RSS Lane (Interval-Driven):** Aggregates deeper macro/crypto news via RSS feeds, evaluates and ranks articles objectively, and publishes the top selections.

The system leverages LLMs (Gemini/OpenAI) to rewrite content into concise, engaging formats tailored for specific platforms, operating autonomously with state-driven reliability and graceful crash recovery.

## 2. Dual-Lane Pipeline Flow
### RSS Lane (Standard)
- **Collect:** Ingests raw RSS feeds normalized into standard `Article` objects.
- **Deduplicate:** Hard and Soft deduplication to aggressively filter out seen content.
- **Rank:** Applies a deterministic rule-based scoring algorithm (Base Impact, Keyword Caps, Time Decay).
- **Select:** Sorts and selects the top candidates.
- **Summarize:** Routes to LLM to generate platform-compliant content.
- **Publish:** Pushes generated content to configured platforms (e.g., Twitter, Telegram).

### Express Lane (Breaking News)
- **Listen:** Telegram listener detects messages in specified channels.
- **Hard Dedup:** Blocks exact historical duplicates (24h hash window).
- **Keyword Filter:** Fast-pass scoring to drop low-value chatter.
- **Fingerprint Dedup:** Entity-level deduplication (60-minute window) using Proper Nouns to prevent spamming the same event.
- **Throttle:** Configurable minimum time gap (e.g., 3 mins) between posts.
- **Summarize & Publish:** Rapid LLM rewrite and instant publishing with delayed retry mechanisms.

## 3. Future-Proof Routing Architecture
- **Prompt Abstraction Layer:** LLM prompts are fully decoupled. Prompts are resolved dynamically based on `lane` and `platform` configuration via `PROMPT_TEMPLATES`, allowing distinct writing styles (e.g., urgent for Express, neutral for RSS).
- **Config-Driven Platform Mapping:** The `PLATFORM_MAPPING` dictionary globally dictates which lane is allowed to publish to which platform. Listeners are entirely decoupled from publishing destinations.

## 4. State & Idempotency Design
- **SQLite (`data/article_state.db`):** The Single Source of Truth for the RSS article lifecycle (NEW → RANKED → SELECTED → PROCESSING → POSTED).
- **Fingerprinting (`recent_topics`):** Shared across both lanes. Express lane outputs lock fingerprints for 60 minutes. RSS lane verifies against this table to suppress older duplicate articles (Cooldown Suppression Hook).
- **Publisher History (`json`):** Deep plugin-level tracking to prevent duplicate API posting per platform, even during retry logic.

## 5. Key Modules
- `main.py`: The async orchestrator governing the concurrent execution of the Express Listener and the RSS polling loop.
- `express_listener.py`: The event-driven Telegram hook.
- `state_manager.py`: Controls SQLite schema, WAL transactions, and fingerprint/cooldown state logic.
- `summarize.py`: Resolves dynamic prompts and routes requests to LLMs (OpenAI/Gemini) with automatic retries and rate-limit backing off.
- `publisher.py`: Translates verified articles into REST API calls for mapped platforms via a unified engine.
- `config.py`: The central nervous system containing all global variables, toggle flags, API Keys, Platform Mappings, Prompt Templates, and RSS source configurations.

## 6. Current Operational Status
- **Phase 9 Completed:** The Dual-Lane V2 Architecture is structurally sealed, feature-complete, and rigorously decoupled.
- **Future Ready:** Capable of scaling entirely new Lanes or Platforms by solely injecting them into the `PLATFORM_MAPPING` and `PROMPT_TEMPLATES` config engine without tearing down core executors.
