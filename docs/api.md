# API And Integration Surface

SOUL does not expose a REST, GraphQL, or WebSocket API in this repository.
The public integration surfaces are:

- the `soul` CLI
- the Python `PresenceRuntime` class
- the Telegram bot runner built on top of `PresenceRuntime`

## Top-Level CLI Contract

| Command | Behavior | Output style |
| --- | --- | --- |
| `soul chat` | Start the interactive companion REPL. | Rich terminal UI with streaming replies |
| `soul drift` | Show recorded personality-state history. | Table |
| `soul milestones` | Show relationship timeline events. | Table |
| `soul status` | Summarize runtime health, counts, mood, features, and proactive state. | Table |
| `soul run-jobs` | Run the enabled maintenance pipeline once. | Success line plus JSON summary |
| `soul telegram-bot` | Start Telegram polling for the allowed chat. | Status table, then long-running process |
| `soul config` | Print redacted runtime configuration. | JSON |
| `soul version` | Print installed version. | Plain text |

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

With no subcommand, `soul db` behaves like `soul db init`.

| Command | Behavior |
| --- | --- |
| `soul db init` | Create runtime directories and initialize the SQLite schema. |
| `soul db rebuild-fts` | Rebuild the SQLite FTS5 index for episodic memories. |

### `soul debug`

These commands are intended for inspection and machine-readable troubleshooting.

| Command | Behavior | Output style |
| --- | --- | --- |
| `soul debug last-turn` | Show the most recent stored turn trace. | JSON |
| `soul debug show-mood` | Show the latest stored mood snapshot. | JSON |
| `soul debug show-facts` | Show the exported story payload. | JSON |
| `soul debug show-memories --limit N` | Show top memories with metadata. | JSON |
| `soul debug show-personality --limit N` | Show recorded personality-state history. | JSON |
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
- runs the same mood, context, generation, and post-processing pipeline as the
  CLI
- closes the session by default
- exports session-end memories by default when the session closes

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

- provider: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`,
  `MOOD_OPENAI_MODEL`
- storage: `DATABASE_URL`, `SOUL_DATA_DIR`, `SOUL_USER_ID`, `SOUL_TIMEZONE`
- feature flags: `ENABLE_TELEGRAM`, `ENABLE_VOICE`, `ENABLE_PROACTIVE`,
  `ENABLE_REFLECTION`, `ENABLE_DRIFT`, `ENABLE_BACKGROUND_JOBS`
- voice: `ELEVENLABS_*`, `VOICE_TRANSCRIPTION_MODEL`
- telegram: `TELEGRAM_*`
- retrieval tuning: `MEMORY_*`, `HMS_*`, `HYBRID_*`

Most bootstrapped commands fail fast if required provider or feature config is
missing.
