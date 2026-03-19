# Modules

## `soul/cli.py`

- Typer entrypoint.
- Owns chat REPL, memory/story/evolution/status/admin commands.
- Integrates Rich live streaming for assistant output.

## `soul/core/`

- `soul_loader.py`: loads/validates soul YAML and compiles immutable prompt.
- `llm_client.py`: provider abstraction + streaming + offline fallback.
- `mood_engine.py`: mood classification and Redis-backed companion state.
- `context_builder.py`: assembles prompt context (mood/story/memory/recent messages).
- `post_processor.py`: story updates, milestones, shared language, turn/session memory extraction.

## `soul/memory/`

- `fts.py`: SQLite FTS5 index helpers and FTS query helpers.
- `embedder.py`: optional local sentence-transformers embedding helper.
- `episodic.py`: repository for episodic writes/retrieval/top/cold/boost/decay/clear.
- `scorer.py`: HMS formulas, temporal decay, and tier transitions.
- `retriever.py`: top-candidate retrieval (FTS top-20) + semantic/HMS rerank + retrieval-time score updates.
- `vector_store.py`: local store + optional Chroma hybrid backend.
- `user_story.py`: user story schema/repository and heuristic extraction.
- `shared_language.py`: recurring phrase tracking.

## `soul/evolution/`

- `drift_engine.py`: bounded weekly personality drift.
- `milestone_tracker.py`: milestone persistence.
- `reflection.py`: monthly reflection generation.

## `soul/tasks/`

- `consolidate.py`: consolidation pipeline + archive/purge retention.
- `hms_decay.py`: nightly HMS decay orchestration.
- `drift_weekly.py`: weekly drift task + resonance signal derivation.
- `proactive.py`: proactive trigger candidate generation + deduped delivery.

## `soul/db.py`

- DB bootstrap and data-access helpers for sessions, messages, milestones, memories, HMS score rows.
- Maintains additive schema initialization for compatibility.

## `soul/models/`

- dataclass models for memory/story/session/drift surfaces, including `MemoryScore`.
