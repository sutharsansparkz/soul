# SOUL

SOUL is a terminal-first AI companion with a fixed identity, emotional context, relational memory, and a path toward slow personality drift.

This repository now contains a fuller local-to-production runtime:

- `soul chat` starts a REPL session.
- `soul chat` now shows a compact turn trace before each reply so you can see the current mood/context pipeline, and assistant output streams directly into the terminal instead of waiting for a final pasted block.
- `soul chat --voice` now supports a mic-first loop: press Enter to record a turn, or type normally if you prefer. `soul chat --voice --record-seconds 5` seeds the first turn from the microphone, and `soul chat --voice-input path.wav --voice` supports file transcription plus synthesized replies when voice credentials are configured.
- `soul db init` initializes local storage.
- `soul memories`, `soul story`, `soul drift`, `soul milestones`, and `soul status` expose the persistence layer.
- `soul memories` now shows HMS-ranked memory tiers with score bars; `soul memories search` performs unified search across episodic + manual memory with HMS-aware ranking; `soul memories top|cold|boost` expose vivid/cold/manual-boost workflows; and `soul memories clear` clears all memory surfaces.
- `soul story edit` opens the profile in your configured editor when `SOUL_EDITOR`, `VISUAL`, or `EDITOR` is set.
- `soul telegram-bot` runs the Telegram polling surface when both a bot token and the allowed chat id are configured.
- One API key, everything. The OpenAI key powers chat, mood classification, story extraction, and monthly reflection. No second vendor, no extra credentials, no model mismatch risk.
- Mood classification uses a short OpenAI chat completion prompt (model: `gpt-4o-mini` by default) - the same API key, no extra downloads, no HuggingFace dependency. Configure the model via `MOOD_OPENAI_MODEL` in your `.env` file.
- Maintenance now includes consolidation, resonance-based drift, proactive reach-out dispatch, monthly reflection generation, and archival/purge of raw session transcripts after retention windows. When LLM credentials are configured, consolidation can enrich the user profile with structured goals, fears, relationships, and shared phrases from completed sessions.
- `make test` runs the local test suite as `python -m pytest -q` after verifying Python `>=3.11` and `pytest` are installed.
- `make docker-test` builds the test image, starts the Compose services, and runs the suite inside Docker.

## Documentation

- `docs/architecture.md` for runtime architecture and data flow
- `docs/modules.md` for package/module responsibilities
- `docs/api.md` for CLI and runtime interface contract
- `docs/memory-schema.md` for memory/profile schema and HMS formulas
- `docs/cli-reference.md` for command quick reference
- `docs/testing.md` for test coverage and execution notes

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[all]
cp .env.example .env
soul db init
soul chat
```

Local test runs need the dev extra from `pyproject.toml` because `requirements.txt` only tracks runtime dependencies. Install it with:

```bash
pip install -e '.[dev]'
```

The project requires Python `3.11+`.

## Docker

```bash
make docker-test
```

`make docker-test` uses Docker Compose under the hood, so Docker Desktop or another local Docker engine must be running and the Docker CLI must be available on `PATH`.

Note: the default Compose stack binds Redis to `127.0.0.1` only for local development, and it should not be exposed publicly without authentication.

The container entrypoints for `worker` and `beat` now launch Celery directly, so the runtime matches the background job model instead of a custom polling loop.

## Known limitations

`get_settings()` uses `@lru_cache`, so changes to `.env` after the process starts are ignored. Restart the worker, beat, or app processes after changing any environment variable.

The `drift_log` schema in `pr.txt` lists `JSONB` columns. The SQLite path stores these as `TEXT` containing valid JSON. If you migrate to PostgreSQL, alter those columns to `JSONB` manually after the initial table creation.

## Current Scope

The implementation includes the main architecture from the design spec:

- soul loading from `soul_data/soul.yaml`
- immutable prompt compilation
- `DATABASE_URL`-driven persistence with SQLite-first storage and additive schema migrations
- configurable runtime state via `SOUL_DATA_DIR`
- OpenAI mood classification with Redis-backed companion state
- user story, milestones, shared language, consolidation, resonance-based weekly drift, monthly reflection, and proactive reach-out candidate generation
- FTS-backed episodic retrieval (`memory_fts`) with HMS scoring (`memory_scores`)
- optional hybrid local embeddings (`HYBRID_EMBEDDINGS=true`) stored in SQLite `embedding` BLOB column
- CLI chat, status, maintenance commands, and Telegram/voice integration hooks

External-service prerequisites still matter: real LLM calls need provider keys, Telegram needs a bot token plus `TELEGRAM_CHAT_ID`, ElevenLabs needs voice credentials, and local transcription needs `whisper` plus audio tooling.
