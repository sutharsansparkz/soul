# Architecture

SOUL is a terminal-first companion system with four runtime layers:

- Soul layer: immutable identity prompt loaded from `soul_data/soul.yaml`.
- Emotional layer: mood inference + companion state persistence (`soul/core/mood_engine.py`).
  Companion state decays toward a neutral baseline after the configured decay window.
- Memory layer: episodic/semantic memory, HMS scoring, user story, shared language.
- Evolution/presence layer: drift, milestones, reflection, proactive triggers, voice, Telegram.

## Request flow (`soul chat`)

1. Start session in DB (`sessions`, `messages`).
2. Analyze user mood and state.
3. Build context:
   - mood tags
   - immutable soul prompt
   - story summary
   - memory snippets (retrieved via SQLite FTS5 top-20 candidates reranked by HMS)
4. Stream assistant reply with Rich live rendering.
5. Persist turn and run post-processing:
   - story updates
   - milestones/shared language
   - turn-level memory extraction
6. On session close, export session-end episodic memory chunks and mark exported.

## Memory architecture

- Persistent SQL tables:
  - `memories` (legacy/manual notes)
  - `episodic_memory` (durable episodic entries)
  - `memory_scores` (HMS components + composite)
- Search layer:
  - SQLite FTS5 virtual table (`memory_fts`) + triggers on `episodic_memory`
  - optional local sentence-transformers cosine signal from `episodic_memory.embedding` BLOB
- Retrieval blend:
  - `final_rank = semantic_similarity * 0.55 + hms_score * 0.45`
  - optional hybrid mode: `(bm25*0.35 + cosine*0.20) + hms*0.45`
  - passive retrieval excludes `cold` tier
  - retrieval updates `R` (`ref_count`), recomputes HMS, and updates retrieval metadata

## Background jobs

- Nightly consolidation (`02:00`): consolidate sessions, story updates, archive old raw messages.
- Nightly HMS decay (`02:30`): recompute temporal component and tier transitions.
- Weekly drift (`sun 03:00`): bounded personality dimension updates.
- Daily proactive presence (`09:00`): trigger-based reach-out candidate generation + delivery.
- Monthly reflection (`day 1 04:00`): reflective summary memory.

## Storage and compatibility

- DB is initialized via `db.init_db()` with additive table/index creation plus FTS5 trigger/index setup.
- Legacy records remain supported via backfill on retrieval (missing SQL score rows are created lazily).
- Settings are process-scoped and lru-cached. Env changes require process restart.
- PostgreSQL deployments should alter `drift_log` JSON columns to `JSONB` after first init.
- Cold memories are retained and searchable; memories with `hms_score < 0.05` are cold and passive context injection excludes them.
