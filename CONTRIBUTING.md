# Contributing

Thanks for taking an interest in SOUL.

This project moves fastest when changes stay aligned with the current
SQLite-first CLI runtime, so a little upfront context goes a long way.

## Development Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install the editable package with dev dependencies:

```bash
pip install -e ".[dev]"
```

Install frontend dependencies for the React CLI:

```bash
npm --prefix ui/cli install
```

3. Copy `.env.example` to `.env`.
4. Set `OPENAI_API_KEY` before running commands that bootstrap the full
   runtime. Set `OPENAI_BASE_URL` only when you are using a non-default
   OpenAI-compatible endpoint, and update `LLM_MODEL` / `MOOD_OPENAI_MODEL`
   if your provider needs different model names.
5. Initialize local state with:

```bash
soul db init
```
6. Run `soul config` if you want to confirm the resolved settings with secrets
   redacted.

Optional features:

- Install `pip install -e ".[voice]"` before enabling `ENABLE_VOICE=true`.
- Install `pip install -e ".[hybrid]"` before enabling
  `HYBRID_EMBEDDINGS=true`.
- Do not enable Telegram or voice until the matching credentials are present in
  `.env`.

## Recommended Workflow

- Keep changes small and focused.
- Prefer updating docs and tests alongside behavior changes.
- Preserve the current local-first architecture unless the change explicitly
  aims to replace it.
- Avoid reintroducing old JSON-file state paths that the current startup
  validator rejects.

## Tests

Run the relevant checks before opening a PR:

```bash
make test
make lint
```

Helpful focused commands:

```bash
python -m pytest -q tests/test_cli_contract.py
python -m pytest -q tests/test_runtime_pipeline.py
python -m pytest -q tests/presence/test_telegram.py
node --check ui/cli/src/dispatch.mjs
node --check ui/cli/src/index.mjs
node --check ui/cli/src/reconciler.mjs
```

Notes:

- `make lint` currently runs `compileall` as a sanity check.
- Tests marked `live_llm` are opt-in and need real provider credentials.

## Docs

If you change public behavior, update the relevant docs in the same PR:

- `README.md` for onboarding or project positioning
- `docs/cli-reference.md` for command surface changes
- `docs/api.md` for interface-level behavior
- `docs/architecture.md` or `docs/modules.md` for structural changes
- `docs/memory-schema.md` for persistence or retrieval changes

## Pull Requests

Good PRs usually include:

- a short summary of what changed
- why the change was needed
- tests run locally
- any config, migration, or compatibility notes

If a change intentionally leaves old scaffolding in place, call that out
explicitly so the next pass can clean it up deliberately.
