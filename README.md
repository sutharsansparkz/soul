# SOUL

SOUL is a terminal-first AI companion with a fixed identity, emotional context, relational memory, and a path toward slow personality drift.

This repository now contains a fuller local-to-production runtime:

- `soul chat` starts a REPL session.
- `soul chat --voice` now supports a mic-first loop: press Enter to record a turn, or type normally if you prefer. `soul chat --voice --record-seconds 5` seeds the first turn from the microphone, and `soul chat --voice-input path.wav --voice` supports file transcription plus synthesized replies when voice credentials are configured.
- `soul db init` initializes local storage.
- `soul memories`, `soul story`, `soul drift`, `soul milestones`, and `soul status` expose the persistence layer.
- `soul memories` now shows HMS-ranked memory tiers with score bars; `soul memories search` reranks semantic candidates with HMS; `soul memories top|cold|boost` expose vivid/cold/manual-boost workflows; and `soul memories clear` clears all memory surfaces.
- `soul story edit` opens the profile in your configured editor when `SOUL_EDITOR`, `VISUAL`, or `EDITOR` is set.
- `soul telegram-bot` runs the Telegram polling surface when a bot token is configured.
- LLM calls use Anthropic first, OpenAI second, and fall back to an offline heuristic companion response when keys are missing or unavailable.
- Mood state can persist in Redis, episodic memory uses a local fallback plus optional Chroma, and background jobs can run through the bundled worker/beat processes or the Celery app entrypoint.
- Maintenance now includes consolidation, resonance-based drift, proactive reach-out dispatch, monthly reflection generation, and archival/purge of raw session transcripts after retention windows. When LLM credentials are configured, consolidation can enrich the user profile with structured goals, fears, relationships, and shared phrases from completed sessions.
- `docker compose up -d app worker beat postgres redis chroma` brings up the containerized runtime.
- `docker compose run --rm test` executes the test suite inside the image.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[all]
copy .env.example .env
soul db init
soul chat
```

## Docker

```bash
docker compose build
docker compose up -d app worker beat postgres redis chroma
docker compose run --rm test
```

Docker Desktop or another local Docker engine must be running before those commands will succeed.

The container entrypoints for `worker` and `beat` now launch Celery directly, so the runtime matches the background job model instead of a custom polling loop.

## Current Scope

The implementation includes the main architecture from the design spec:

- soul loading from `soul_data/soul.yaml`
- immutable prompt compilation
- `DATABASE_URL`-driven persistence with SQLite for direct local use and Postgres in the Compose stack
- configurable runtime state via `SOUL_DATA_DIR`
- heuristic mood detection with optional transformers classifier and Redis-backed companion state
- user story, milestones, shared language, consolidation, resonance-based weekly drift, monthly reflection, and proactive reach-out candidate generation
- hybrid episodic memory using local JSONL fallback plus optional Chroma
- CLI chat, status, maintenance commands, and Telegram/voice integration hooks

External-service prerequisites still matter: real LLM calls need provider keys, Telegram needs a bot token, ElevenLabs needs voice credentials, and local transcription needs `whisper` plus audio tooling. Chroma is disabled by default for direct local CLI runs to keep the process lifecycle clean, but Compose enables it for containerized environments.
