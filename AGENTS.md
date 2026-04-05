# Agent Instructions (SOUL CLI)

This repository is a local-first AI companion implemented as a Python package with a CLI (`soul`) backed by SQLite.
This file is meant to help automated agents contribute safely and effectively.

## What to build (product intent)
- The primary user journey is `soul chat`: interactive REPL (React dispatcher + Ink chat UI), streamed responses, SQLite-backed sessions/messages, and post-turn memory/state updates.
- Optional surfaces reuse the same core pipeline:
  - Telegram bot (`soul telegram-bot`)
  - Voice helpers (`soul chat --voice`)
- Maintenance (`soul run-jobs`) runs consolidation/decay/drift/reflection/proactive jobs.

## High-signal entry points (start here)
- CLI entrypoint: `soul/cli.py`
  - Public command entrypoint + React dispatcher handoff
- React CLI frontend: `ui/cli/src/dispatch.mjs`
  - Non-chat command UX rendered by custom `react-reconciler`
- Ink chat frontend: `ui/cli/src/index.mjs`
  - Interactive chat interface
- CLI bridge modules: `soul/cli_support/react_bridge.py` and `soul/cli_support/ink_bridge.py`
  - Connect React/Ink frontend calls to Python runtime behavior
- Core turn orchestrator: `soul/conversation/orchestrator.py`
  - Mood analysis -> context build -> LLM call -> persistence -> async post-processing -> trace write
- Prompt assembly: `soul/core/context_builder.py`
  - Memory retrieval + prompt sections ordering
- Mood classification: `soul/core/mood_engine.py`
  - Provider call + validation + fail-safe fallback
- LLM provider client: `soul/core/llm_client.py`
  - Streaming + retries
- SQLite schema/migrations: `soul/persistence/sqlite_setup.py`
- SQLite engine + connection settings: `soul/persistence/db.py` and `soul/db.py`
- Memory retrieval: `soul/memory/retrieval/retriever.py`

## How to set up development
- Python: **3.11+**
- Install (dev): `pip install -e ".[dev]"`
- Local runtime uses `soul_data/` under the repo root by default (see `.env.example`).

## How to run verification (do this before PR)
- Unit tests: `python -m pytest -q`
- Compile/import sanity: `make lint` (or `python -m compileall soul`)

## DB + schema conventions (important)
- The runtime is SQLite-only.
- Repository code should use the existing SQL helpers in:
  - `soul/persistence/db.py`
  - `soul/db.py`
- When touching schema:
  - Update `soul/persistence/sqlite_setup.py`
  - Ensure tests still pass
  - Keep migrations idempotent and backward-compatible for existing local DBs
- Foreign keys must be enforced:
  - Ensure `PRAGMA foreign_keys = ON` is enabled in the engine connect hook (both engine paths).

## Testing conventions
- Prefer contract-style tests (CLI outputs, persistence behavior, retrieval ranking, file permissions).
- For DB-related tests, follow the existing pattern:
  - `db.init_db(settings.database_url)`
  - use `tmp_path`-scoped SQLite databases
- CLI tests use `typer.testing.CliRunner`.

## Security + safety rules for agents
- Never commit secrets (`.env`, API keys, voice tokens).
- Assume user-provided text (CLI, Telegram, voice transcription) can be adversarial:
  - keep SQL parameterized
  - avoid shell injection patterns when invoking external editors/commands
- Be careful with file operations:
  - enforce restrictive permissions where the code already does so
  - do not widen permissions for sensitive artifacts.

## Architectural “do not break” boundaries
- `ConversationOrchestrator.run_turn()` is the single-turn lifecycle.
  - If you add/modify behavior, update trace payload fields deterministically.
- Retrieval: `ContextBuilder` should avoid DB mutations during prompt building.
  - `MemoryRetriever` supports gating mutations during retrieve; use that rather than introducing side effects.
- CLI should not rewire internal dependencies after constructing orchestrator objects.

## Change workflow recommendation
1. Identify the exact contract failing in tests (run `python -m pytest -q`).
2. Fix the smallest component that restores the contract.
3. Add/adjust tests when you harden behavior or add invariants.
4. Re-run the full suite and compile sanity check.
