# Documentation

These docs describe the current SOUL runtime as it exists in this repository
today: a SQLite-first, terminal-first companion system with optional Telegram
and voice surfaces.

## Start Here

- `README.md` for first-time setup and project overview
- `docs/cli-reference.md` for the fastest way to find commands
- `docs/testing.md` if you are contributing or validating changes

## Core Runtime Docs

- `docs/architecture.md` explains startup, turn flow, presence surfaces, and
  maintenance jobs.
- `docs/modules.md` maps the current package layout and major responsibilities.
- `docs/api.md` describes the public CLI and Python integration surfaces.
- `docs/memory-schema.md` documents the SQLite persistence model, HMS scoring,
  and retrieval behavior.

## Design Docs

- `docs/soul-design.md` explains the soul document contract and design
  principles.
- `docs/drift-algorithm.md` explains how bounded personality drift works.

## Scope Note

The repo still contains some older compatibility and deployment scaffolding.
Where that differs from the main runtime, these docs favor the current,
tested CLI plus SQLite workflow rather than the older paths.
