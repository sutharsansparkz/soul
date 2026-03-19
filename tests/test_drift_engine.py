from __future__ import annotations

from soul.evolution.drift_engine import SOUL_BASELINE, run_weekly_drift


def test_weekly_drift_applies_small_adjustments():
    current = dict(SOUL_BASELINE)
    signals = {"warmth_expression": 1.0, "directness": -1.0}

    updated = run_weekly_drift(current, signals)

    assert updated["warmth_expression"] == 0.51
    assert updated["directness"] == 0.49


def test_weekly_drift_is_clamped_to_baseline_window():
    current = {key: 0.7 for key in SOUL_BASELINE}
    signals = {key: 1.0 for key in SOUL_BASELINE}

    updated = run_weekly_drift(current, signals)

    assert all(value <= 0.7 for value in updated.values())
    assert all(0.3 <= value <= 0.7 for value in updated.values())


def test_weekly_drift_uses_only_known_state_dimensions_and_ignores_extra_signals():
    current = dict(SOUL_BASELINE)
    signals = {
        "humor_intensity": 1.0,
        "ignored_signal": 1.0,
    }

    updated = run_weekly_drift(current, signals)

    assert updated["humor_intensity"] == 0.51
    assert "ignored_signal" not in updated
