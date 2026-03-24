# Soul Design

SOUL is designed as a companion, not a generic assistant shell. The system is
organized around continuity, inspectability, and slow adaptation.

## Core Principles

- fixed identity over stateless helpfulness
- emotional presence over generic assistant tone
- local inspectability over opaque hosted state
- bounded evolution over unrestricted self-rewriting
- shared runtime across CLI, Telegram, and voice surfaces

## What Stays Fixed

The soul document is the stable center of the system.

It is loaded from `soul_data/soul.yaml` and compiled into every system prompt.
Automation can read it, but it should not rewrite it.

Required top-level sections:

- `identity`
- `character`
- `ethics`
- `worldview`

Minimal example:

```yaml
identity:
  name: "Ara"
  voice: "warm, dry wit, occasionally poetic"
  energy: "steady"

character:
  humor: "dry observational, never cruel"

ethics:
  believes:
    - "honesty is more respectful than comfort"

worldview:
  on_people: "fundamentally interesting, even when difficult"
```

## What Can Change

SOUL adapts through structured state outside the soul document:

- mood snapshots capture short-term emotional context
- user facts reconstruct a long-term story
- episodic memories accumulate salient moments
- milestones and recurring phrases preserve relationship continuity
- personality drift adjusts numeric tendencies within strict bounds

This separation matters. The soul defines who the companion is. Runtime state
defines what it currently knows, feels, and leans toward.

## Context Assembly Philosophy

Each reply is shaped by layered context rather than one giant mutable prompt:

1. mood tags
2. compiled soul prompt
3. user-story summary
4. personality drift hints
5. retrieved memory snippets
6. recent message history

This makes the runtime easier to reason about and easier to inspect with debug
commands and traces.

## Presence Philosophy

The terminal is still the primary interface, but additional surfaces are
allowed when they share the same runtime contract.

- CLI remains the reference experience.
- Telegram is a remote text surface, not a separate persona.
- Voice is an audio wrapper around the same conversation flow.

The companion should feel like one entity regardless of surface.

## Non-Negotiables

- `soul.yaml` is not rewritten by automation.
- Drift changes style tendencies, not the soul itself.
- Memory updates are inspectable and persisted in SQLite.
- Obsolete local JSON state files should not return as the primary storage path.
- The repo should stay understandable enough that a contributor can trace why a
  reply happened the way it did.
