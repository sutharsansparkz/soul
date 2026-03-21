from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from soul import db
from soul.config import Settings
from soul.evolution.drift_engine import SOUL_BASELINE, run_weekly_drift
from soul.tasks.drift_weekly import derive_resonance_signals, run_drift_task


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


def test_weekly_drift_returns_current_state_when_disabled(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        drift_enabled=False,
    )
    current = dict(SOUL_BASELINE)
    current["warmth_expression"] = 0.63

    updated = run_weekly_drift(current, {"warmth_expression": 1.0}, settings=settings)

    assert updated == current


def test_run_drift_task_skips_writes_when_disabled(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)
    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        drift_enabled=False,
    )
    personality_path = tmp_path / "personality.json"
    log_path = tmp_path / "drift_log.json"
    existing = dict(SOUL_BASELINE)
    existing["directness"] = 0.62
    personality_path.write_text(json.dumps(existing, ensure_ascii=True), encoding="utf-8")

    result = run_drift_task(personality_path, log_path, {"directness": 1.0}, settings=settings)

    assert result.updated == existing
    assert json.loads(personality_path.read_text(encoding="utf-8")) == existing
    assert not log_path.exists()
    assert db.list_drift_log(database_url) == []


def test_derive_resonance_signals_ignores_sessions_older_than_30_days(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    old_session = db.create_session(database_url, "Ara")
    db.log_message(
        database_url,
        session_id=old_session,
        role="assistant",
        content="What part of that felt most overwhelming and why does it matter so much to you right now?",
        companion_state="warm",
    )
    db.log_message(
        database_url,
        session_id=old_session,
        role="user",
        content="I feel stressed about the launch because the deadline keeps moving and I am carrying too much alone.",
        user_mood="stressed",
        companion_state="warm",
    )
    db.close_session(database_url, old_session)

    recent_session = db.create_session(database_url, "Ara")
    db.close_session(database_url, recent_session)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    old_timestamp = (now - timedelta(days=31)).isoformat()
    recent_timestamp = (now - timedelta(days=1)).isoformat()
    with db.connect(database_url) as connection:
        connection.execute(
            text("UPDATE sessions SET started_at = :started_at, ended_at = :ended_at WHERE id = :session_id"),
            {
                "started_at": old_timestamp,
                "ended_at": old_timestamp,
                "session_id": old_session,
            },
        )
        connection.execute(
            text("UPDATE sessions SET started_at = :started_at, ended_at = :ended_at WHERE id = :session_id"),
            {
                "started_at": recent_timestamp,
                "ended_at": recent_timestamp,
                "session_id": recent_session,
            },
        )
        connection.commit()

    signals = derive_resonance_signals(database_url)

    assert signals == {
        "humor_intensity": 0.0,
        "response_length": 0.0,
        "curiosity_depth": 0.0,
        "directness": 0.0,
        "warmth_expression": 0.0,
    }
