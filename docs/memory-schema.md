# Memory and Profile Schema

## `user_story.json`

The user story profile tracks:

- basic user identity
- current chapter summary
- active goals and fears
- important moments
- relationships
- observed values
- triggers
- things the user loves

## `episodic_memory`

Suggested fields:

- `id`
- `user_id`
- `session_id`
- `timestamp`
- `content`
- `emotional_tag`
- `importance`
- `memory_type`
- `ref_count`

## `drift_log`

Suggested fields:

- `id`
- `run_date`
- `dimensions_before`
- `dimensions_after`
- `resonance_signals`
- `notes`

These shapes are kept small on purpose so the nightly consolidation job can synthesize them reliably.
