# API And Integration Surface

SOUL does not expose a REST, GraphQL, or WebSocket API in this repository.
The public integration surfaces are:

- the `soul` CLI
- the Python `PresenceRuntime` class
- the Telegram bot runner built on top of `PresenceRuntime`

Implementation note:

- the public CLI entrypoint still lives at `soul/cli.py`
- `soul/cli.py` dispatches through the React CLI frontend in `ui/cli/`
- command execution logic remains in Python under `soul/cli_support/`
- this internal split does not change the public command surface described
  below

## Top-Level CLI Contract

Direct commands:

| Command | Behavior | Output style |
| --- | --- | --- |
| `soul init` | Run the guided config builder and bootstrap the local runtime. | Rich prompts plus summary table |
| `soul chat` | Start the interactive companion REPL. | React dispatcher + Ink chat UI |
| `soul ink-chat` | Launch the chat UI directly. | Ink chat UI |
| `soul drift` | Show recorded personality-state history. | Table |
| `soul milestones` | Show relationship timeline events. | Table |
| `soul status` | Summarize runtime health, counts, mood, features, and proactive state. | Table |
| `soul run-jobs` | Run the enabled maintenance pipeline once. | Table plus success line |
| `soul telegram-bot` | Start Telegram polling for the allowed chat. | Status table, then long-running process |
| `soul config` | Print redacted runtime configuration. | JSON |
| `soul version` | Print installed version. | Plain text |

Command groups:

| Command | Behavior | Output style |
| --- | --- | --- |
| `soul memories` | Memory inspection and search helpers. | Tables |
| `soul story` | Reconstructed story inspection and editing helpers. | Story view plus editor flow |
| `soul db` | Database bootstrap and FTS maintenance helpers. | Help or success lines |
| `soul debug` | Stored diagnostics and inspection helpers. | Mixed table and JSON output |

## Command Groups

### `soul memories`

With no subcommand, `soul memories` prints stored memories ranked by HMS score.

| Command | Behavior |
| --- | --- |
| `soul memories search "<query>"` | Search episodic memories and show reranked results. |
| `soul memories top` | Show the highest-ranked vivid memories. |
| `soul memories cold` | Show memories currently in the cold tier. |
| `soul memories boost "<query>"` | Boost the best matching memory by flagging it. |
| `soul memories clear` | Confirm and delete stored memory rows for the current user. |

### `soul story`

With no subcommand, `soul story` prints the reconstructed user-story view.

| Command | Behavior |
| --- | --- |
| `soul story edit` | Export the story payload to a temp JSON file, optionally open an editor, then import changes back into SQLite. |

### `soul db`

With no subcommand, `soul db` prints help for the database command group.

| Command | Behavior |
| --- | --- |
| `soul db init` | Create runtime directories and initialize the SQLite schema. |
| `soul db rebuild-fts` | Rebuild the SQLite FTS5 index for episodic memories. |

### `soul debug`

These commands are intended for inspection and troubleshooting.

| Command | Behavior | Output style |
| --- | --- | --- |
| `soul debug last-turn` | Show the most recent stored turn trace. | JSON |
| `soul debug show-mood` | Show the latest stored mood snapshot. | Table |
| `soul debug show-facts` | Show the exported story payload. | JSON |
| `soul debug show-memories --limit N` | Show top memories with metadata. | Table |
| `soul debug show-personality --limit N` | Show recorded personality-state history. | Table |
| `soul debug show-trace <trace-id>` | Show a specific trace by id. | JSON |
| `soul debug explain-memory <memory-id>` | Show the stored row for one memory. | JSON |

## Chat Options And In-Session Commands

`soul chat` supports:

- `--voice`
- `--replay`
- `--voice-input PATH`
- `--record-seconds N`

Inside a chat session, the slash commands are:

| Command | Behavior |
| --- | --- |
| `/quit` | Exit the session cleanly. |
| `/save <note>` | Save a manual memory note. |
| `/mood` | Show the current mood snapshot for the session. |
| `/story` | Print the current reconstructed story. |
| `/voice on|off` | Toggle voice output and mic-first behavior for the session. |

Voice notes:

- `--voice` and `/voice on` only work when `ENABLE_VOICE=true`.
- Startup validation requires valid `ELEVENLABS_*` credentials plus the
  `whisper` and `sounddevice` packages.
- If recording is unavailable at runtime, chat falls back to typed input while
  keeping voice output enabled.
- `soul chat` and `soul ink-chat` use the same Python orchestration pipeline.

## Python Integration

The cleanest importable surface is `PresenceRuntime`.

```python
from soul.presence.runtime import PresenceRuntime

runtime = PresenceRuntime()
result = runtime.handle_text("hello")
print(result.reply_text)
```

`PresenceRuntime.handle_text()`:

- creates a session if one is not supplied
- creates the provided `session_id` if it does not already exist
- runs the same mood, context, generation, and post-processing pipeline as the
  CLI
- closes the session by default
- exports session-end memories by default when the session closes
- lets callers keep a session open by passing `close_session=False`
- lets callers override end-of-session export behavior with
  `export_session_end=...`

The returned `PresenceTurnResult` includes:

- `session_id`
- `user_text`
- `reply_text`
- `provider`
- `model`
- `fallback_used`
- `metadata` with `companion_state`, `user_mood`, and `trace_id`

## Telegram Contract

`soul telegram-bot` and `TelegramBotRunner` follow these rules:

- Telegram must be enabled with `ENABLE_TELEGRAM=true`.
- Both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be configured.
- Only the configured chat id is allowed to interact with the bot.
- Unauthorized chats are ignored and do not mutate memory, story, or
  milestones.
- Telegram uses the same persistence and post-processing pipeline as the CLI.

## Configuration Contract

Important environment groups:

- provider: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_*`, `MOOD_OPENAI_*`
- storage: `DATABASE_URL`, `SOUL_DATA_DIR`, `SOUL_USER_ID`, `SOUL_TIMEZONE`
- feature flags: `ENABLE_TELEGRAM`, `ENABLE_VOICE`, `ENABLE_PROACTIVE`,
  `ENABLE_REFLECTION`, `ENABLE_DRIFT`, `ENABLE_BACKGROUND_JOBS`
- voice: `ELEVENLABS_*`, `VOICE_TRANSCRIPTION_MODEL`
- telegram: `TELEGRAM_*`
- retrieval tuning: `MEMORY_*`, `HMS_*`, `HYBRID_*`
- maintenance and drift tuning: `DRIFT_*`, `PROACTIVE_*`,
  `MAINTENANCE_AUTO_INTERVAL`

Most bootstrapped commands fail fast if required provider or feature config is
missing.

The practical inspection surface for this contract is `soul config`, which
prints the resolved settings with secrets redacted.

For first-run setup, `soul init` writes a local `.env` and prepares the
default SQLite-backed runtime directories and files.
