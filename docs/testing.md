# Testing Strategy

This scaffold uses contract-style tests to lock the SOUL MVP spec before the runtime exists.

The current suite focuses on:

- soul document structure and prompt compilation expectations
- drift caps and weekly adjustment rules
- user story schema shape
- CLI command surface

These tests are intentionally self-contained so they can run without the application package being implemented yet.

## Dockerized Path

The production-oriented scaffold also exposes the same validation inside Docker:

```bash
docker compose build
docker compose up -d redis chroma postgres
docker compose run --rm test
```

That path is wired through the `test` service in `docker-compose.yml` so the app image, runtime dependencies, and test runner stay aligned.
