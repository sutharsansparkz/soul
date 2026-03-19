# SOUL Design

SOUL is a terminal-only companion with a fixed identity and evolving relationship state.

## Core Layers

- `Soul layer`: immutable identity, ethics, character, and worldview.
- `Emotional layer`: user mood detection and companion state management.
- `Memory layer`: episodic memory, user story, and shared language.
- `Evolution layer`: drift, milestones, and self-reflection.
- `Presence layer`: optional voice, Telegram, and proactive reach-out.

## Non-Negotiables

- The soul document is never rewritten by automation.
- Personality drift is slow, bounded, and reversible only within the allowed range.
- Memory is consolidated after the fact, not mutated in real time.
- The terminal is the primary interface.

## Soul Document Shape

The immutable soul document should define:

- `identity`
- `character`
- `ethics`
- `worldview`

Those sections are compiled into the system prompt for every LLM call.
