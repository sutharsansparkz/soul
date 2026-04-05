# Modules

## Top-Level Entry Points

- `soul/cli.py`: public CLI entrypoint. It dispatches to the React frontend by
  default and uses an internal bypass to run Typer commands for backend calls.
- `ui/cli/`: React-based CLI frontend package.
  - `src/index.mjs`: Ink chat UI.
  - `src/dispatch.mjs`: dispatcher UI powered by a custom `react-reconciler`
    host renderer.
  - `src/reconciler.mjs`: custom React host config that renders dispatcher
    output to the terminal.
- `soul/cli_support/`: feature-oriented CLI implementation modules for runtime
  bootstrap, chat, memories, story flows, status/milestones, and debug output.
- `soul/config.py`: Pydantic settings model, path helpers, and redacted config
  export.
- `soul/db.py`: compatibility-oriented database helper facade used by tests and
  some command paths.
- `scripts/install-git-hooks.sh`: helper for installing the repository git
  hooks locally.

## Package Map

### `soul/cli_support/`

Internal command implementations used by `soul/cli.py`.

- `runtime.py` owns secure path creation, bootstrap helpers, and the guided
  `soul init` config builder flow.
- `chat.py` owns the interactive chat loop, local runtime shortcuts, voice
  helpers, and in-session slash command handling.
- `memories.py` renders memory views and keeps ranking/formatting helpers in
  one place.
- `story.py` renders the user story and handles the external-editor import flow.
- `status.py` groups status, milestones, drift history, maintenance, and
  Telegram command helpers.
- `debug.py` renders trace, mood, memory, and personality inspection commands.
- `ink_bridge.py` exposes session start/turn/close bridge calls for the Ink
  chat frontend.
- `react_bridge.py` exposes command invocation output as JSON for the dispatcher
  frontend.

### `soul/bootstrap/`

Startup and validation helpers.

- `validator.py` checks schema availability, provider config, timezone validity,
  feature-specific requirements, and obsolete legacy files.
- `feature_registry.py` defines the feature-flag registry used at startup.
- `errors.py` centralizes runtime-specific exception types.
- `logging.py` and `config.py` provide bootstrap-level helpers.

### `soul/conversation/`

Turn orchestration glue for the main runtime.

- `orchestrator.py` owns the read/generate/write flow and stored turn traces.
- `context_loader.py` wraps context assembly.
- `extractor.py`, `prompt_builder.py`, `post_processor.py`, and `responder.py`
  are supporting modules that keep the orchestration layer segmented.

### `soul/core/`

Core runtime behavior that every surface depends on.

- `soul_loader.py` loads `soul.yaml` and compiles the immutable system prompt.
- `context_builder.py` assembles mood, story, drift, memory, and history into
  one prompt bundle.
- `llm_client.py` talks to OpenAI-compatible chat providers and supports
  streaming responses.
- `mood_engine.py` classifies user mood and derives companion state.
- `post_processor.py` updates story facts, milestones, recurring phrases, and
  memory records after each turn.
- `presence_context.py` derives proactive and status context from stored data.

### `soul/llm/`

LLM-related helper types and parsers.

- `client.py`, `schemas.py`, and `parsers.py` provide supporting abstractions
  around provider payloads and structured parsing.

### `soul/maintenance/`

One-shot maintenance and background-job logic.

- `jobs.py` is the current main entrypoint for maintenance execution and the
  auto-trigger throttle used after chat sessions.
- `consolidation.py` processes completed sessions and extracts structured
  insights.
- `decay.py` recomputes HMS memory state.
- `drift.py` derives resonance signals and writes bounded personality updates.
- `reflection.py` stores reflection artifacts.
- `proactive.py` refreshes and optionally delivers reach-out candidates.

### `soul/memory/`

Memory and user-story domain logic.

- `episodic.py` exposes the SQLite-backed episodic-memory repository.
- `fts.py` exposes lightweight helpers around the SQLite FTS index.
- `scorer.py` defines HMS components, decay, tiers, and composite scoring.
- `retriever.py` is a compatibility layer; `retrieval/` contains the active
  ranking and hybrid retrieval logic.
- `embedder.py` optionally adds local sentence-transformer embeddings.
- `user_story.py` defines the in-memory `UserStory` model and extraction rules.
- `shared_language.py` contains recurring phrase logic.
- `vector_store.py` defines the shared record format and memory block rendering.

### `soul/memory/repositories/`

Database-backed repositories for runtime entities.

- `messages.py` handles sessions and message history.
- `user_facts.py` reconstructs and persists the user story.
- `episodic.py` persists episodic memories and applies retrieval boosts.
- `mood.py`, `milestones.py`, `personality.py`, `reflections.py`,
  `proactive.py`, and `maintenance.py` handle their corresponding entities.
- `app_settings.py` and `shared_language.py` support lightweight state storage.

### `soul/observability/`

Inspection and tracing helpers.

- `traces.py` stores and retrieves turn traces.
- `debug.py`, `diagnostics.py`, and `metrics.py` group supporting observability
  helpers.

### `soul/persistence/`

Low-level SQLite access and schema management.

- `db.py` owns engine creation and connection helpers.
- `sqlite_setup.py` creates tables, indexes, and FTS triggers.
- `models.py` stores lightweight persistence-oriented structures.

### `soul/presence/`

Adapters for non-CLI interaction surfaces.

- `runtime.py` exposes `PresenceRuntime`, the shared single-turn integration
  surface.
- `telegram.py` implements polling, single-chat enforcement, and message send
  logic.
- `voice.py` handles recording, transcription, synthesis, and playback.

### `soul/state/`

Pure state helpers and bounded-drift rules.

- `drift.py` defines the baseline personality dimensions and weekly update rule.
- `mood.py`, `milestones.py`, and `personality.py` group lightweight state
  helpers.

## Tests

The `tests/` tree is contract-heavy and covers:

- CLI surface and runtime behavior
- guided setup and config bootstrap behavior
- fail-fast startup rules
- HMS scoring and retrieval
- story extraction and milestone generation
- presence adapters
- maintenance jobs and proactive delivery rules
- security and safety guards around persistence helpers

When the code and docs disagree, the tests are usually the best indicator of
the intended contract.
