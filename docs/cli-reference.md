# CLI Reference

Installed entrypoint:

```bash
soul
```

Development equivalent:

```bash
python -m soul.cli
```

## Bootstrap And Introspection

```bash
soul db init
soul db rebuild-fts
soul config
soul version
```

- `soul db init` creates runtime directories and initializes the SQLite schema.
- `soul db rebuild-fts` rebuilds the episodic-memory FTS5 index.
- `soul config` prints redacted runtime settings as JSON.
- `soul version` prints the installed version string.

## Chat

```bash
soul chat
soul chat --replay
soul chat --voice
soul chat --voice-input sample.wav --voice
soul chat --record-seconds 5 --voice
```

Notes:

- `soul chat` streams replies directly in the terminal.
- The chat UI prints a compact turn trace before each reply.
- `--voice` is feature-gated by `ENABLE_VOICE=true`.
- `--voice-input` and `--record-seconds` use the same voice bridge as the live
  voice mode.

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

All `debug` commands print JSON.

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
