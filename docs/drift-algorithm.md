# Drift Algorithm

SOUL's personality drift is a slow numeric adaptation layer. It changes how the
companion leans over time without rewriting the underlying soul document.

## Personality Dimensions

The tracked dimensions are:

- `humor_intensity`
- `response_length`
- `curiosity_depth`
- `directness`
- `warmth_expression`

All dimensions start from the same baseline value of `0.5`.

## Guardrails

- Drift only applies when both `ENABLE_DRIFT=true` and `DRIFT_ENABLED=true`.
- Each maintenance run can move a dimension by at most
  `DRIFT_WEEKLY_RATE` (default `0.01`).
- Each dimension is clamped to `baseline +/- DRIFT_MAX_DEVIATION`
  (default `0.20`).
- Unknown dimensions in the signal payload are ignored.
- The soul document in `soul.yaml` is never rewritten by drift.

## Resonance Signal Derivation

Resonance signals are derived from completed sessions inside the configured
lookback window.

The current algorithm:

1. Load recent completed sessions within `DRIFT_SIGNAL_LOOKBACK_DAYS`.
2. Pair each assistant message with the following user message.
3. Estimate engagement from the user's word count.
4. Add a mood bonus for emotionally salient moods such as `reflective`,
   `venting`, and `celebrating`.
5. Accumulate dimension-specific evidence:
   - long assistant replies support `response_length`
   - question marks and curious states support `curiosity_depth`
   - warm or concerned states support `warmth_expression`
   - playful states support `humor_intensity`
   - short direct replies to deep user messages support `directness`
6. Normalize final signals into the range `-1.0 .. 1.0`.

If no qualifying conversation pairs exist, all signals resolve to `0.0`.

## Update Rule

Given the current state and a signal value:

`new_value = current_value + signal * DRIFT_WEEKLY_RATE`

The result is then clamped to the allowed range around the baseline.

Because the update rate is small and the state is bounded, drift stays gradual
even when the same signal persists for many runs.

## Persistence

Each successful drift run records a new row in `personality_state` containing:

- the updated dimension values
- the resonance signals that produced the change
- version metadata and source notes

If drift is disabled, the current state is returned unchanged and no new row is
written.

## Prompt Injection

Personality state influences replies through prompt context, not through
rewriting the soul.

Only dimensions whose delta exceeds
`PERSONALITY_DRIFT_RENDER_THRESHOLD` are rendered into the system prompt. When
present, the drift section is injected after the user-story summary and before
retrieved memory snippets.

## Design Goal

The desired effect is subtle adaptation:

- warmer when the relationship consistently rewards warmth
- more curious when the user responds well to deeper questions
- more direct or playful when the conversation history supports it

The companion should feel more attuned over time without becoming a copy of the
user or drifting away from its original identity.
