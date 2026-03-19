# SOUL Documentation Scaffold

This directory holds the spec-level references for the SOUL CLI MVP.

The docs are intentionally short and implementation-oriented:

- `docs/soul-design.md` covers the identity, emotional, memory, and evolution layers.
- `docs/memory-schema.md` defines the key persisted data shapes.
- `docs/drift-algorithm.md` captures the personality drift rules and limits.
- `docs/cli-reference.md` lists the command surface for the initial CLI.
- `docs/testing.md` explains the contract-test approach used in this scaffold.
- The container/runtime layer lives in `Dockerfile`, `docker-compose.yml`, and `Makefile`.
- `make docker-test` or `docker compose run --rm test` runs the test suite inside the app image.
- `docker compose up -d app worker beat postgres redis chroma` starts the full local stack.
- The `worker` and `beat` services execute Celery directly, not a custom polling loop.

The goal is to keep the architecture readable before the runtime exists.
