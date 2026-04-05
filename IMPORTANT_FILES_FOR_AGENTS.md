# Important Files for AI Agents

This is a quick index so an automated agent can jump directly to the “right”
places without rediscovering the tree.

## Runbooks / verification
- `README.md`
- `docs/testing.md`
- `.github/workflows/test.yml` (CI behavior)
- `Makefile` (local helper commands)

## Local configuration
- `.env.example` (what env vars to set)
- `soul/config.py` (the `Settings` contract and aliases)

## CLI / core runtime
- `soul/cli.py` (public CLI entrypoint, React dispatcher handoff, backend bypass)
- `ui/cli/src/dispatch.mjs` (React dispatcher UI for non-chat commands)
- `ui/cli/src/index.mjs` (Ink chat UI)
- `ui/cli/src/reconciler.mjs` (custom `react-reconciler` host renderer)
- `soul/cli_support/react_bridge.py` (command execution bridge for dispatcher)
- `soul/cli_support/ink_bridge.py` (turn/session bridge for chat UI)
- `soul/conversation/orchestrator.py` (single-turn lifecycle + trace writes)
- `soul/core/context_builder.py` (prompt assembly + memory injection rules)
- `soul/core/mood_engine.py` (mood classification + fail-safe fallback)
- `soul/core/llm_client.py` (LLM streaming + retries)

## Persistence / schema
- `soul/persistence/db.py` and `soul/db.py` (engine + connection pragmas)
- `soul/persistence/sqlite_setup.py` (schema creation + migrations + FTS triggers)
- `soul/memory/repositories/*` (domain repositories)

## Maintenance jobs
- `soul/maintenance/jobs.py` (background schedule throttling)
- `soul/maintenance/consolidation.py` (unit-of-work consolidation flow)
- `soul/maintenance/*.py` (decay/drift/reflection/proactive)

## Tests
- `tests/conftest.py` (global fixtures + live_llm gating)
- `tests/test_*` (contract suite)
