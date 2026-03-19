# Memory and Profile Schema

## `user_story.json`

Top-level shape:

- `user_id`
- `updated_at`
- `basics` (`name`, `location`, `occupation`, optional `birthday`)
- `current_chapter` (`summary`, `active_goals`, `active_fears`, `current_mood_trend`)
- `big_moments`
- optional `upcoming_events` (dated entries)
- `relationships`
- `values_observed`
- `triggers`
- `things_they_love`

Backward compatibility: missing optional keys are defaulted during load.
Database bootstrap also performs additive HMS column migrations for legacy SQLite/PostgreSQL rows.

## `episodic_memory` table

- `id` (pk)
- `user_id`
- `session_id`
- `timestamp`
- `content`
- `emotional_tag`
- `memory_type`
- `word_count`
- `flagged`
- `ref_count`
- `tier` (`vivid|present|fading|cold`)

## `memory_scores` table

- `memory_id` (pk, fk -> `episodic_memory.id`)
- `user_id`
- `score_emotional` (E)
- `score_retrieval` (R)
- `score_temporal` (T)
- `score_flagged` (F)
- `score_volume` (U)
- `hms_score` (composite)
- `last_computed`
- `last_retrieved`
- `decay_rate`

Composite formula:

`S = E*0.35 + R*0.25 + T*0.20 + F*0.10 + U*0.10`

Retrieval blend formula:

`final_score = semantic_score*0.55 + hms_score*0.45`

Retrieval-time update contract:

- increment `ref_count` (`R++`)
- recompute HMS composite + tier
- persist score/tier metadata to SQL + vector store

## `drift_log` table

- `id`
- `run_date`
- `dimensions_before`
- `dimensions_after`
- `resonance_signals`
- `notes`

## Retention and archival

- raw session messages are archived to `soul_data/logs/archive/*.jsonl`
- default retention is 90 days (`RAW_RETENTION_DAYS`)
- purge occurs only after archive write succeeds
