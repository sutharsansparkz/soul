"""Drift state helpers."""

from __future__ import annotations

from soul.config import Settings
from soul.memory.repositories.personality import PersonalityStateRepository


SOUL_BASELINE: dict[str, float] = {
    "humor_intensity": 0.5,
    "response_length": 0.5,
    "curiosity_depth": 0.5,
    "directness": 0.5,
    "warmth_expression": 0.5,
}


def merge_with_baseline(current: dict[str, float] | None) -> dict[str, float]:
    merged = dict(SOUL_BASELINE)
    if current:
        for key, value in current.items():
            if key in SOUL_BASELINE:
                merged[key] = float(value)
    return merged


def run_weekly_drift(
    current: dict[str, float],
    resonance_signals: dict[str, float],
    *,
    settings: Settings,
) -> dict[str, float]:
    current = merge_with_baseline(current)
    if not settings.drift_enabled:
        return current

    updated: dict[str, float] = {}
    for dimension, value in current.items():
        signal = resonance_signals.get(dimension, 0.0)
        baseline = SOUL_BASELINE.get(dimension, value)
        new_value = value + (signal * settings.drift_weekly_rate)
        lower = baseline - settings.drift_max_deviation
        upper = baseline + settings.drift_max_deviation
        updated[dimension] = round(max(lower, min(upper, new_value)), 4)
    return updated


def get_drift_snapshot(settings: Settings) -> dict[str, object]:
    from soul.maintenance.drift import derive_resonance_signals

    return {
        "personality_state": PersonalityStateRepository(settings.database_url, user_id=settings.user_id).get_current_state(),
        "resonance_signals": derive_resonance_signals(settings.database_url, settings=settings),
    }
