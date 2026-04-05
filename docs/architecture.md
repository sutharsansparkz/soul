# Architecture

## Supported Runtime

SOUL is currently implemented and documented as a local CLI application backed
by SQLite. The CLI and the optional presence surfaces all share the same core
conversation pipeline and the same persistence layer.

The major runtime layers are:

- CLI frontend layer:
  - `ui/cli/src/dispatch.mjs` renders command execution UX with a custom
    `react-reconciler` host renderer
  - `ui/cli/src/index.mjs` renders interactive chat with Ink
- CLI entrypoint: `soul/cli.py` is the public `soul` command and bridges
  frontend calls to Python command execution
- CLI support layer: `soul/cli_support/` holds the command implementations for
  runtime bootstrap, chat, memory views, story flows, status, and debug output
- bootstrap: settings, feature registry, startup validation, schema readiness
- conversation: turn orchestration and context loading
- core: soul loading, mood analysis, prompt assembly, and post-processing
- memory and state: facts, episodic memory, milestones, drift state, and traces
- presence: CLI, Telegram, and voice adapters
- maintenance: consolidation, decay, drift, reflection, and proactive jobs
- observability: status views, debug commands, and stored turn traces

## Startup Flow

Most user-facing commands bootstrap in the following order:

1. `soul/cli.py` dispatches to the React CLI frontend (`ui/cli/`), installing
   frontend dependencies when needed.
2. The frontend invokes Python backend commands through bridge modules in
   `soul/cli_support/`.
3. Python backend command paths load `Settings` from environment variables and
   `.env`.
4. Create local runtime paths with runtime helpers in
   `soul/cli_support/runtime.py`.
5. Run `validate_startup()` to verify:
   - a SQLite URL is configured
   - the timezone is valid
   - the database can be opened
   - the schema can be created or reused
   - provider configuration exists
   - enabled features have the required credentials and dependencies
   - obsolete JSON state files are not still present in `SOUL_DATA_DIR`
6. Load the immutable soul document from `soul_data/soul.yaml`.
7. Hand off to the command handler or presence surface.

`soul config`, `soul version`, and `soul db init` are lighter-weight entry
points and do not run the full chat bootstrap path. `soul db` with no
subcommand prints group help.

The `soul init` first-run setup path is also lighter-weight than the chat
bootstrap. It writes a local `.env`, creates secure runtime directories, and
initializes SQLite without requiring the full provider validation needed for
conversation commands.

## Conversation Flow

The main request path for `soul chat`/`soul ink-chat` and `PresenceRuntime`
looks like this:

1. Create or resume a session in `sessions`.
2. Analyze the new user message with `MoodEngine`.
3. Persist the user message and a mood snapshot.
4. Build context with `ContextBuilder`:
   - mood tags
   - compiled soul prompt from `soul.yaml`
   - user-story summary reconstructed from `user_facts`
   - current personality drift hints
   - retrieved memory snippets from `episodic_memories`
   - recent message history
   - prompt-time retrieval is read-only; `ContextBuilder` passes
     `mutate_on_retrieve=False` so prompt assembly does not update memory state
5. Send the assembled prompt to `LLMClient`, which streams the reply back to the
   terminal when applicable.
6. Persist the assistant reply.
7. Run `PostProcessor` to update facts, milestones, recurring phrases, and
   high-signal memories.
8. Write a stored turn trace with prompt sections, retrieved memory metadata,
   provider details, and post-processing outputs.
9. When the session closes, export any new session-end memory chunks into the
   episodic-memory store.

Some simple runtime queries, such as local time checks, can be answered without
calling the LLM provider.

## Presence Surfaces

SOUL exposes one shared runtime across multiple interaction surfaces:

- CLI: the primary experience, with React frontend UX in `ui/cli/` and
  feature-specific backend behavior in `soul/cli_support/`.
- Telegram: `TelegramBotRunner` uses `PresenceRuntime`, enforces a single
  allowed chat, and stores message history in the same database as the CLI.
- Voice: `VoiceBridge` handles recording, Whisper transcription, ElevenLabs
  synthesis, and local playback without creating a separate conversation path.

All of these surfaces reuse the same orchestration, storage, and
post-processing logic.

## Maintenance Flow

The one-shot maintenance entrypoint is `soul run-jobs`, which calls
`run_enabled_maintenance()` and records job results in `maintenance_runs`.

Depending on feature flags, a run can include:

- consolidation: process completed sessions that have not yet been consolidated
- decay: recompute HMS components and cold-tier transitions
- drift: derive resonance signals and record a bounded personality-state update
- reflection: generate monthly reflection artifacts
- proactive: refresh reach-out candidates and optionally deliver them through
  Telegram

The same maintenance pipeline can also be auto-triggered after a chat session
ends. `trigger_maintenance_if_due()` runs the work in a background thread and
rate-limits it with `MAINTENANCE_AUTO_INTERVAL`, so the interactive CLI does
not block on every session close.

## Storage Layout

Core local filesystem paths:

- `soul_data/soul.yaml`
- `soul_data/db/soul.db`
- `soul_data/logs/latest_session.log`
- `soul_data/logs/archive/`
- `soul_data/exports/`
- `soul_data/tmp/`
- `soul_data/voice/` when voice features are used

Core SQLite tables include:

- `users`, `sessions`, `messages`
- `user_facts`, `shared_language_entries`
- `milestones`, `personality_state`, `reflection_artifacts`
- `proactive_candidates`, `maintenance_runs`, `turn_traces`
- `episodic_memories` plus the `episodic_memories_fts` FTS5 virtual table

Schema setup is additive, so new installs and existing local databases can be
bootstrapped through the same initialization path.

## Observability

SOUL keeps the runtime inspectable without a separate observability service:

- `soul status` prints a human-readable summary of sessions, mood, features, and
  proactive candidates.
- `soul config` prints a redacted settings snapshot.
- `soul init` writes a first-run config and bootstraps the local runtime.
- `soul debug ...` commands expose stored traces, facts, moods, memories, and
  personality state through a mix of JSON and rich table output.
- failed generations also produce stored traces, which makes debugging easier
  after the fact.

## Compatibility Notes

- The canonical runtime is SQLite-first. Some helper functions and compatibility
  tables remain for older code paths and tests.
- The repository still includes some compatibility-oriented helpers, but the
  maintained runtime path is the local CLI plus SQLite workflow described in
  these docs.
