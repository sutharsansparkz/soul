# Memory And Persistence Schema

## Canonical Storage Model

The current SOUL runtime stores state in SQLite, not in long-lived JSON state
files. Story facts, episodic memories, milestones, reflections, proactive
candidates, and turn traces all live in the database.

Startup validation explicitly rejects obsolete legacy files such as
`user_story.json`, `personality.json`, and `shared_language.json` when they are
found in `SOUL_DATA_DIR`.

## Reconstructed User Story

The user story is reconstructed from `user_facts` rows and exposed as the
`UserStory` shape used by `soul story` and `soul story edit`.

Top-level story fields:

- `user_id`
- `updated_at`
- `basics`
- `current_chapter`
- `big_moments`
- `upcoming_events`
- `relationships`
- `values_observed`
- `triggers`
- `things_they_love`

Important nested fields:

- `basics`: `name`, `location`, `occupation`, optional `birthday`
- `current_chapter`: `summary`, `active_goals`, `active_fears`,
  `current_mood_trend`
- `big_moments`: dated major life events with emotional weight metadata

`soul story edit` exports this shape to a temporary JSON file, then imports the
edited payload back into `user_facts`.

## Core Relational Tables

General runtime tables:

- `users`
- `sessions`
- `messages`
- `maintenance_runs`
- `turn_traces`

Relational context tables:

- `user_facts`
- `shared_language_entries`
- `milestones`
- `personality_state`
- `reflection_artifacts`
- `proactive_candidates`

## `episodic_memories`

`episodic_memories` is the canonical store for long-term conversational memory.

Important columns:

- `id`
- `user_id`
- `session_id`
- `label`
- `content`
- `emotional_tag`
- `memory_type`
- `source`
- `created_at`
- `updated_at`
- `observed_at`
- `word_count`
- `flagged`
- `ref_count`
- `tier`
- `score_emotional`
- `score_retrieval`
- `score_temporal`
- `score_flagged`
- `score_volume`
- `hms_score`
- `last_computed`
- `last_retrieved`
- `decay_rate`
- `embedding`
- `metadata_json`

Tier meanings:

- `vivid`: highly retrievable and emotionally salient
- `present`: active long-term context
- `fading`: still retained but lower-priority
- `cold`: retained but excluded from passive retrieval

Default thresholds:

- cold: below `HMS_COLD_THRESHOLD` (default `0.05`)
- vivid: `>= 0.75`
- present: `>= 0.40`
- fading: everything else above the cold threshold

## HMS Scoring

The Human Memory Scoring model uses five normalized components:

- emotional intensity
- retrieval count
- temporal recency
- manual flagging
- memory volume

Composite formula:

`hms_score = E*0.35 + R*0.25 + T*0.20 + F*0.10 + U*0.10`

Important details:

- `score_retrieval` grows with `log1p(ref_count)` and asymptotically approaches
  `1.0`.
- `score_temporal` decays exponentially using `HMS_DECAY_HALFLIFE_DAYS`.
- `score_flagged` becomes `1.0` when a memory is manually boosted.
- `score_volume` saturates around 120 words.

## FTS And Retrieval

SQLite FTS5 powers the first retrieval stage through the
`episodic_memories_fts` virtual table.

FTS-indexed fields:

- `label`
- `content`
- `emotional_tag`
- `memory_type`

The FTS table is linked to `episodic_memories` through insert, update, and
delete triggers, so it stays in sync automatically.

Retrieval flow:

1. Fetch up to `MEMORY_CANDIDATE_K` FTS matches.
2. Normalize BM25 scores into a `0..1` similarity signal.
3. Optionally blend in local embedding cosine similarity when hybrid
   embeddings are enabled and available.
4. Compute final rank using dynamic weights:

`rank = semantic_component + hms_component + recency_bonus`

Important ranking details:

- When embeddings are available, the retriever uses the configured
  `HMS_SEMANTIC_WEIGHT` and `HMS_SCORE_WEIGHT`.
- Without embeddings, it falls back to a simpler `0.40` semantic / `0.60` HMS
  split.
- Vivid or manually flagged memories get a small extra HMS-weight boost.
- Recently observed memories can receive a small recency bonus for the first
  week after `observed_at`.
- Passive retrieval excludes cold memories. Explicit search commands include
  them.

Retrieval-time side effects:

- Prompt building is read-only. `ContextBuilder` retrieves with
  `mutate_on_retrieve=False`, so assembling a prompt does not change memory
  state.
- Default interactive retrieval increments `ref_count`.
- Default interactive retrieval recomputes HMS components.
- Default interactive retrieval updates `last_retrieved`.
- Default interactive retrieval refreshes tier and stored score fields.

Passive retrieval excludes cold memories. Explicit search commands can include
them.

## Related Context Tables

- `user_facts`: normalized storage for story reconstruction
- `shared_language_entries`: recurring phrases and their meanings
- `milestones`: relationship events such as anniversaries, streaks, and major
  life moments
- `personality_state`: recorded drift snapshots and resonance signals
- `reflection_artifacts`: stored reflection summaries plus structured insights
- `proactive_candidates`: queued or delivered reach-out candidates
- `turn_traces`: stored per-turn diagnostics and prompt metadata

## Compatibility Notes

The repo still contains older helper paths and cleanup logic for tables such as
`memories`, `memory_scores`, and `episodic_memory`. They remain useful for
compatibility and tests, but the main runtime writes and reads through
`episodic_memories` and the repository layer built around it.
