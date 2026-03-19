# SOUL Documentation

This directory documents the implemented SOUL CLI runtime and its production-facing behavior.

## Core references

- `docs/architecture.md`: runtime architecture, request/data flow, and background jobs.
- `docs/modules.md`: package/module map with ownership and responsibilities.
- `docs/api.md`: command and runtime interfaces (CLI + in-session command contract).
- `docs/cli-reference.md`: quick command reference.
- `docs/memory-schema.md`: persisted memory/profile schema, HMS scoring model, and retrieval behavior.
- `docs/drift-algorithm.md`: weekly personality drift constraints and update logic.
- `docs/soul-design.md`: high-level design principles and non-negotiables.
- `docs/testing.md`: test coverage and execution path.

## Operational notes

- Local bootstrap: initialize DB with `soul db init`, then start with `soul chat`.
- Local Python runtime: use Python `3.11+`.
- Background jobs: `celery -A soul.tasks worker --loglevel=info` and `celery -A soul.tasks beat --loglevel=info`.
- Containerized stack: `docker compose up -d app worker beat redis`.
- Telegram surface: configure both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; updates from other chats are ignored.
- Default persistence is SQLite + Redis. Legacy compatibility dependencies live behind `pip install -e '.[legacy]'`.
