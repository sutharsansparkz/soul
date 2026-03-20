# API and Interfaces

SOUL does not expose an HTTP API in this repository. The public interface is CLI + scheduled tasks.

## CLI surface

Core:

- `soul chat`
- `soul chat --voice`
- `soul chat --replay`
- `soul status`
- `soul run-jobs`
- `soul db init`
- `soul config`

Memory:

- `soul memories`
- `soul memories search "<query>"`
- `soul memories top`
- `soul memories cold`
- `soul memories boost "<query>"`
- `soul memories clear`

Profile/evolution:

- `soul story`
- `soul story edit`
- `soul drift`
- `soul milestones`
- `soul telegram-bot`

In-session commands (`soul chat`):

- `/quit`
- `/save "note"`
- `/mood`
- `/story`
- `/voice on|off`

## Configuration variables (key subset)

- `LLM_MAX_TOKENS` — maximum tokens for Anthropic completions (default: 800)

## Memory command contracts

- `soul memories`:
  - HMS-sorted list with score bar + tier.
- `soul memories search`:
  - unified search across episodic HMS memory and manual SQL memory.
  - merged ranking includes semantic relevance and HMS/importance score.
  - source label is shown per row (`episodic` or `manual`).
- `soul memories clear`:
  - clears legacy SQL memories, episodic SQL rows/scores, and the local JSONL fallback surface.

## HMS retrieval contract

- Candidate fetch size: `MEMORY_CANDIDATE_K` (default `20`).
- Candidate source: SQLite FTS5 (`memory_fts`) where available.
- Reranking formula:
  - `rank = semantic_similarity * HMS_SEMANTIC_WEIGHT + hms_score * HMS_SCORE_WEIGHT`
  - defaults: `0.55` and `0.45`.
- Optional hybrid mode:
  - semantic term can be composed from `bm25*0.35 + cosine*0.20` while preserving total `0.55` semantic weight.
- Retrieval updates:
  - increment `ref_count` (`R++`)
  - recompute HMS components and tier
  - update SQL score row + retrieval metadata

## Scheduled task interfaces

Celery task names:

- `soul.tasks.consolidate.nightly_consolidation_task`
- `soul.tasks.hms_decay.nightly_hms_decay_task`
- `soul.tasks.drift_weekly.weekly_drift_task`
- `soul.tasks.proactive.proactive_presence_task`
- `soul.evolution.reflection.monthly_reflection_task`

## Telegram surface

- `soul telegram-bot` runs in single-chat mode.
- Both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be configured.
- Incoming updates from other chats are ignored and do not mutate story, memory, or milestones.
