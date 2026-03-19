# Architecture

SOUL is a terminal-first companion system with four runtime layers:

- Soul layer: immutable identity prompt loaded from `soul_data/soul.yaml`.
- Emotional layer: mood inference + companion state persistence (`soul/core/mood_engine.py`).
- Memory layer: episodic/semantic memory, HMS scoring, user story, shared language.
- Evolution/presence layer: drift, milestones, reflection, proactive triggers, voice, Telegram.

## Request flow (`soul chat`)

1. Start session in DB (`sessions`, `messages`).
2. Analyze user mood and state.
3. Build context:
   - mood tags
   - immutable soul prompt
   - story summary
   - memory snippets (retrieved via semantic top-20 candidates reranked by HMS)
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
- Vector layer:
  - local JSONL vector fallback
  - optional Chroma (hybrid mode)
- Retrieval blend:
  - `final_rank = semantic_similarity * 0.55 + hms_score * 0.45`
  - passive retrieval excludes `cold` tier
  - retrieval updates `R` (`ref_count`), recomputes HMS, syncs SQL/vector metadata

## Background jobs

- Nightly consolidation (`02:00`): consolidate sessions, story updates, archive old raw messages.
- Nightly HMS decay (`02:30`): recompute temporal component and tier transitions.
- Weekly drift (`sun 03:00`): bounded personality dimension updates.
- Daily proactive presence (`09:00`): trigger-based reach-out candidate generation + delivery.
- Monthly reflection (`day 1 04:00`): reflective summary memory.

## Storage and compatibility

- DB is initialized via `db.init_db()` with additive table/index creation.
- Legacy records remain supported via backfill on retrieval (missing SQL score rows are created lazily).
- Cold memories are retained and searchable; passive context injection excludes them.
