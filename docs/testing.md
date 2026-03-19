# Testing Strategy

The project uses contract-style tests to keep the CLI/runtime behavior aligned with `pr.txt`.

## Local Path

For local runs, install the test extra from `pyproject.toml` so `pytest` is available:

```bash
pip install -e '.[dev]'
```

`requirements.txt` tracks runtime dependencies only, so it may not include test tooling.

`make test` runs the suite as `python -m pytest -q`, which matches the Makefile's module-based invocation.

The current suite focuses on:

- soul document structure and prompt compilation expectations
- drift caps and weekly adjustment rules
- user story schema shape
- CLI command surface
- persona regression fixtures (20+ deterministic conversation turns)
- HMS scoring formula, retriever reranking, and nightly decay idempotency
- SQLite FTS schema/search contracts and legacy migration compatibility
- unified memory search/clear CLI contracts and retrieval update behavior
- consolidation retention safety and settings-aware persistence behavior

These tests are intentionally deterministic so they can run in CI without network-dependent model calls.

## Dockerized Path

The production-oriented scaffold also exposes the same validation inside Docker:

```bash
make docker-test
```

`make docker-test` wraps `scripts/docker-test.sh`, which builds the test image, starts `redis`, and runs the suite in the `test` service against the default SQLite-backed runtime. Docker Desktop or Docker Engine must be installed, and the Docker CLI must be on `PATH`, for that path to work.
