# Testing

## Testing Philosophy

SOUL relies on contract-style tests more than golden snapshots of internal
implementation details. Most tests create temporary SQLite databases and assert
user-visible behavior:

- command surfaces
- fail-fast startup rules
- persistence contracts
- retrieval ranking and score updates
- story extraction and milestone generation
- presence surface behavior
- file-permission and safety expectations

That makes the suite a good source of truth when old docs drift.

## Local Test Setup

Install the package with dev dependencies:

```bash
pip install -e ".[dev]"
```

Python `3.11+` is required.

Useful commands:

```bash
make test
make lint
python -m pytest -q
```

Notes:

- `make test` verifies Python 3.11+, checks that `pytest` is installed, and
  runs `python -m pytest -q`.
- `make lint` currently runs `compileall` against `soul/`. It is
  a syntax/import sanity check, not a formatter or style linter.
- `requirements.txt` contains runtime dependencies only, so it does not replace
  the editable dev install for contributors.

## High-Value Test Areas

The current test suite covers:

- soul document loading and prompt compilation
- startup validation and fail-fast architecture rules
- CLI command contract, guided setup, and chat UX
- local runtime shortcuts and streaming behavior
- HMS scoring, decay, retrieval ranking, and FTS integration
- user-story extraction and story editing flows
- milestone generation, reflections, and proactive reach-out logic
- Telegram, voice, and presence-runtime behavior
- config redaction, timezone handling, and file permissions
- SQL safety guards and compatibility helper behavior

## Focused Test Runs

Examples:

```bash
python -m pytest -q tests/test_cli_contract.py
python -m pytest -q tests/test_runtime_pipeline.py
python -m pytest -q tests/test_hms_retriever.py
python -m pytest -q tests/presence/test_telegram.py
```

These are useful when you are changing one area and want faster iteration than a
full-suite run.

For CLI refactors specifically, the contract tests are designed to let the
implementation move between `soul/cli.py` and `soul/cli_support/` without
changing user-visible behavior.

## Live Provider Tests

Some tests are marked `live_llm` and are intended for explicit provider-backed
validation. They should only be run when you want a real networked check.

Example:

```bash
python -m pytest -q -m live_llm
```

Because they depend on real credentials and network availability, they should
not be treated as the default local test path.

## Docker Test Path

This repository does not currently include the Docker-based test scaffold.
Use the local Python + SQLite test path instead (for example `make test` or
`python -m pytest -q`).
