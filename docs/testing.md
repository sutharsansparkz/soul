# Testing Strategy

The project uses contract-style tests to keep the CLI/runtime behavior aligned with `pr.txt`.

The current suite focuses on:

- soul document structure and prompt compilation expectations
- drift caps and weekly adjustment rules
- user story schema shape
- CLI command surface
- persona regression fixtures (20+ deterministic conversation turns)
- HMS scoring formula, retriever reranking, and nightly decay idempotency
- unified memory search/clear CLI contracts and retrieval update behavior
- consolidation retention safety and settings-aware persistence behavior

These tests are intentionally deterministic so they can run in CI without network-dependent model calls.

## Dockerized Path

The production-oriented scaffold also exposes the same validation inside Docker:

```bash
docker compose build
docker compose up -d redis chroma postgres
docker compose run --rm test
```

That path is wired through the `test` service in `docker-compose.yml` so the app image, runtime dependencies, and test runner stay aligned.
