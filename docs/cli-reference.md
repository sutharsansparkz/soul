# CLI Reference

## Core

- `soul chat`
- `soul chat` shows a compact per-turn trace (`inside <name> ...`) before the reply and streams the assistant response token-by-token in the terminal
- `soul chat --voice`
- `soul chat --voice-input "path.wav"`
- `soul chat --record-seconds 5`
- `soul chat --replay`

## Memory

- `soul memories` (HMS-ranked list with score bars and tiers)
- `soul memories search "query"` (unified search across episodic + manual memories, reranked with HMS weighting)
- `soul memories top` (top 10 vivid memories)
- `soul memories cold` (cold-tier memory list)
- `soul memories boost "query"` (manual HMS flag/boost)
- `soul memories clear` (wipes SQL + episodic + optional vector-backed memory state)

## Profile

- `soul story`
- `soul story edit`

## Evolution

- `soul drift`
- `soul milestones`

## Status

- `soul status`
- `soul telegram-bot` (requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`)

## Admin

- `soul run-jobs`
- `soul db init`
- `soul config`

## In-Session Commands

- `/quit`
- `/save "note"`
- `/mood`
- `/story`
- `/voice on | off`
