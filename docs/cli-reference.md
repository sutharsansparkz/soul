# CLI Reference

Installed entrypoint:

```bash
soul
```

`soul` commands run through a React-based dispatcher UI.
Render engines:
- Ink powers the interactive chat surface.
- A custom `react-reconciler` host renderer powers dispatcher output.

Development equivalent:

```bash
python -m soul.cli
```

The public CLI entrypoint stays in `soul/cli.py`, while the heavier command
implementations are organized under `soul/cli_support/`.

Set `SOUL_SKIP_REACT_DISPATCH=1` to run commands directly through Typer without
the React wrapper.

## Bootstrap And Introspection

```bash
soul init
soul db
soul db init
soul db rebuild-fts
soul config
soul version
```

- `soul init` walks through first-run setup, writes a local `.env`, and
  bootstraps the SQLite runtime.
- `soul db` with no subcommand prints help for the database command group.
- `soul db init` creates runtime directories and initializes the SQLite schema.
- `soul db rebuild-fts` rebuilds the episodic-memory FTS5 index.
- `soul config` prints redacted runtime settings as JSON.
- `soul version` prints the installed version string.

## Chat

```bash
soul chat
soul ink-chat
soul chat --replay
soul chat --voice
soul chat --voice-input sample.wav --voice
soul chat --record-seconds 5 --voice
soul ink-chat --install
```

Notes:

- `soul chat` launches the Ink chat surface through the React dispatcher.
- `soul ink-chat` launches the same Ink chat surface directly.
- The chat UI prints a compact turn trace before each reply.
- UI dependencies are auto-installed on first `soul` run when missing.
- `soul ink-chat --install` forces `npm install` for `ui/cli` before launch.
- `--voice` is feature-gated by `ENABLE_VOICE=true`.
- `--voice-input` and `--record-seconds` use the same voice bridge as the live
  voice mode.
- Voice startup validation requires the voice dependencies plus valid
  `ELEVENLABS_*` credentials.

## Story And Memory

```bash
soul memories
soul memories search "launch plan"
soul memories top
soul memories cold
soul memories boost "late night coding"
soul memories clear

soul story
soul story edit
```

- `soul memories` shows stored memories ranked by HMS score.
- `soul memories search` shows reranked episodic-memory matches.
- `soul memories boost` flags the best matching memory and increases its score.
- `soul story` prints the reconstructed user story.
- `soul story edit` exports the story to a temp JSON file and reimports edits.

## Status, Drift, And Maintenance

```bash
soul status
soul drift
soul milestones
soul run-jobs
soul telegram-bot
```

- `soul status` summarizes counts, mood, reach-out candidates, and feature
  state.
- `soul drift` shows recorded personality-state history.
- `soul milestones` shows the relationship timeline.
- `soul run-jobs` executes the enabled maintenance pipeline once.
- `soul telegram-bot` starts polling Telegram for the configured allowed chat.
- `soul telegram-bot` requires `ENABLE_TELEGRAM=true` plus valid
  `TELEGRAM_*` settings.

## Debug

```bash
soul debug last-turn
soul debug show-mood
soul debug show-facts
soul debug show-memories --limit 25
soul debug show-personality --limit 10
soul debug show-trace <trace-id>
soul debug explain-memory <memory-id>
```

Output style:

- JSON: `last-turn`, `show-facts`, `show-trace`, `explain-memory`
- rich tables or human-readable output: `show-mood`, `show-memories`,
  `show-personality`

## In-Session Slash Commands

Inside `soul chat`:

```text
/quit
/save note text
/mood
/story
/voice on
/voice off
```

- `/save` stores a manual memory note for the current session.
- `/voice on` and `/voice off` only work when voice support is enabled.
- When recording is unavailable, `/voice on` still enables spoken replies and
  falls back to typed input.
