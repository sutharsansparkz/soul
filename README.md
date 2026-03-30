# SOUL

SOUL is a terminal-first AI companion with a fixed identity, mood awareness,
episodic memory, slow personality drift, and optional Telegram or voice
surfaces.

At its core, SOUL combines:

- an immutable soul document in `soul_data/soul.yaml`
- OpenAI-compatible chat and mood classification
- SQLite-backed sessions, facts, memories, milestones, reflections, and traces
- post-processing that turns conversations into structured long-term context
- maintenance jobs for consolidation, decay, drift, reflection, and proactive
  reach-out candidates

## Highlights

- `soul chat` runs an interactive REPL and streams replies directly in the
  terminal.
- `soul chat` prints a compact per-turn trace so you can see what parts of the
  runtime are active.
- GitHub Pages deployment is included for a lightweight project site published
  from the `site/` directory.
- `soul chat` can load repo-local `SKILL.md` instructions from your current
  workspace, similar to code agents that honor project guidance files.
- `soul skills` lists built-in workspace skill templates and can scaffold them
  into a target directory.
- `soul memories`, `soul story`, `soul drift`, `soul milestones`, and
  `soul status` let you inspect what the system has learned.
- `soul run-jobs` executes the maintenance pipeline once for the current local
  runtime.
- `soul telegram-bot` reuses the same conversation pipeline from a single
  allowed Telegram chat.
- `soul chat --voice` can record, transcribe, and optionally speak replies when
  voice dependencies are configured.
- `soul debug ...` commands expose stored traces, facts, memories, moods, and
  personality state for debugging.

## Project Status

The primary documented and tested path today is:

- local Python 3.11+
- SQLite storage under `soul_data/`
- the `soul` CLI entrypoint

## Quick Start

### 1. Create a virtual environment

macOS / Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

For the core runtime plus tests:

```bash
pip install -e ".[dev]"
```

Optional extras:

- `pip install -e ".[voice]"` for voice transcription and playback support
- `pip install -e ".[hybrid]"` for local embedding-based hybrid retrieval
- `pip install -e ".[all]"` for everything at once

### 3. Run the guided setup

```bash
soul init
```

The wizard asks for your core provider settings, writes a local `.env`, and
bootstraps the local runtime in one pass.

You can still copy `.env.example` to `.env` and edit it by hand if you prefer.
At minimum you need:

- `OPENAI_API_KEY`
- `LLM_MODEL` and `MOOD_OPENAI_MODEL` if your provider needs non-default model
  names
- `SOUL_TIMEZONE` if you want local time-aware milestones and status output

Set `OPENAI_BASE_URL` only when you are targeting a non-default
OpenAI-compatible endpoint. If you are using the default OpenAI API, leave it
unset or comment it out.

Optional features stay off by default. Only enable `ENABLE_VOICE=true` or
`ENABLE_TELEGRAM=true` after you have configured the matching credentials and
installed the required extras.

Use `soul config` after setup if you want to verify the resolved runtime
settings with secrets redacted.

This creates:

- `soul_data/`
- a default `soul_data/soul.yaml` if one does not exist yet
- `soul_data/db/soul.db`
- session log and archive directories

### 5. Start chatting

```bash
soul chat
```

If you want workspace-specific behavior, place a `SKILL.md` in the current
project root or a nested working directory. `soul chat` will load matching
files from the workspace root down to your current directory, with deeper files
taking precedence.

To scaffold a built-in read-only explorer skill into a project:

```bash
soul skills init file-explorer --dir .
```

Useful next commands:

- `soul status`
- `soul memories`
- `soul story`
- `soul run-jobs`

To publish the project site with GitHub Pages, the repository includes
`.github/workflows/pages.yml`, which deploys the static files under `site/`
whenever `main` is updated.

For the first deployment, GitHub Pages must already be enabled for the
repository with `Settings -> Pages -> Source -> GitHub Actions`, or you can add
a `PAGES_DEPLOY_TOKEN` repository secret so `actions/configure-pages@v5` can
enable Pages automatically. GitHub's `GITHUB_TOKEN` can deploy an existing Pages
site, but it cannot turn Pages on for the repository by itself.

## Release Process

SOUL publishes package releases from `main` only. The repository's
`.github/workflows/release.yml` workflow runs Python Semantic Release after a
merge to `main`, updates the version files plus `CHANGELOG.md`, creates a git
tag, creates a GitHub Release, and uploads the built `dist/` artifacts.

The intended flow is:

- open pull requests into `main`
- let the test workflow pass before merging
- merge to `main`
- allow semantic-release to cut the release automatically

Avoid manually bumping versions on feature branches or deleting `CHANGELOG.md`,
because both are managed by the release automation. For the maintainer checklist
and branch protection settings, see `docs/release-process.md`.

## Configuration

The most important configuration groups are:

- Provider: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_*`, `MOOD_OPENAI_*`
- Storage: `DATABASE_URL`, `SOUL_DATA_DIR`, `SOUL_USER_ID`, `SOUL_TIMEZONE`
- Feature flags: `ENABLE_TELEGRAM`, `ENABLE_VOICE`, `ENABLE_PROACTIVE`,
  `ENABLE_REFLECTION`, `ENABLE_DRIFT`, `ENABLE_BACKGROUND_JOBS`
- Voice: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`,
  `VOICE_TRANSCRIPTION_MODEL`, `VOICE_PLAYBACK_TIMEOUT`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_BASE_URL`
- Retrieval and memory tuning: `MEMORY_*`, `HMS_*`, `HYBRID_*`
- Drift, proactive, and maintenance tuning: `DRIFT_*`, `PROACTIVE_*`,
  `MAINTENANCE_AUTO_INTERVAL`

Notes:

- Most user-facing commands go through startup validation, which means provider
  configuration must be present before commands like `soul chat` or
  `soul status` will run.
- `ENABLE_VOICE=true` requires the voice dependencies plus valid
  `ELEVENLABS_*` credentials.
- `HYBRID_EMBEDDINGS=true` is only useful when the hybrid retrieval dependency
  set is installed.
- `soul init` writes a local `.env` and bootstraps the default SQLite-backed
  runtime files and directories.
- `soul config` prints the currently resolved settings with secrets redacted.
- `get_settings()` is cached for the life of the process, so restart the CLI
  after changing environment variables.
- Startup validation rejects obsolete legacy JSON state files in
  `SOUL_DATA_DIR`; the current runtime expects SQLite-backed state instead.

See `.env.example` for the full set of knobs.

## Command Overview

Top-level commands:

- `soul init` for the guided first-run config and local bootstrap
- `soul chat` for the interactive REPL
- `soul memories` for ranked memory inspection and memory search helpers
- `soul story` for the reconstructed user-story view
- `soul drift` for personality-state history
- `soul milestones` for relationship timeline events
- `soul status` for a runtime summary
- `soul run-jobs` for one-shot maintenance execution
- `soul skills` for listing or scaffolding built-in workspace skills
- `soul telegram-bot` for Telegram polling
- `soul db init` and `soul db rebuild-fts` for database bootstrap and FTS repair
- `soul debug ...` for stored diagnostics and inspection helpers
- `soul config` for redacted runtime configuration
- `soul version` for the installed version string

Inside `soul chat`, the slash commands are:

- `/quit`
- `/save`
- `/mood`
- `/story`
- `/voice on|off`

For examples, see `docs/cli-reference.md`.

## Data And Privacy

SOUL is built around local state:

- the soul document lives in `soul_data/soul.yaml`
- runtime state lives in a local SQLite database by default
- session logs and archives stay under `soul_data/logs/`
- voice recordings and generated audio stay under `soul_data/voice/` when used

On POSIX systems, the runtime creates `soul_data/` with restrictive permissions
and writes sensitive files with owner-only access where possible.

## Development

Common commands:

```bash
make test
make lint
python -m pytest -q
```

Notes:

- `make test` verifies Python 3.11+, checks for `pytest`, then runs
  `python -m pytest -q`.
- `make lint` is currently a compile/import sanity check via `compileall`; it
  is not a style formatter or static-analysis suite.
- Live-provider tests are marked with `@pytest.mark.live_llm` and should only be
  run intentionally with real provider credentials.

## Documentation

- `docs/README.md` - documentation index
- `docs/architecture.md` - runtime architecture and data flow
- `docs/modules.md` - package and module map, including the `soul/cli.py` +
  `soul/cli_support/` split
- `docs/api.md` - CLI and Python integration surfaces
- `docs/cli-reference.md` - quick command reference
- `docs/memory-schema.md` - persistence model, HMS scoring, and retrieval rules
- `docs/drift-algorithm.md` - personality drift model
- `docs/soul-design.md` - design principles and soul-document contract
- `docs/testing.md` - test strategy and execution notes
- `repo_tree.txt` - current repository layout snapshot

## Contributing

See `CONTRIBUTING.md` for local setup, test expectations, and PR guidance.
