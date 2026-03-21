from __future__ import annotations

from datetime import datetime, timezone

from soul.config import Settings
from soul.core import presence_context


def test_build_presence_context_uses_configured_timezone_for_milestones(monkeypatch, tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        timezone_name="Asia/Kolkata",
    )
    fixed_now = datetime(2026, 3, 21, 0, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(
        presence_context.db,
        "get_last_message_timestamp",
        lambda database_url: "2026-03-20T23:45:00+00:00",
    )
    monkeypatch.setattr(
        presence_context.db,
        "list_user_message_moods_since",
        lambda database_url, moods, since=None: [{"created_at": "2026-03-18T12:00:00+00:00", "user_mood": "stressed"}],
    )
    monkeypatch.setattr(
        presence_context.db,
        "list_milestones",
        lambda database_url, limit=200: [
            {"occurred_at": "2025-03-20T21:00:00+00:00", "note": "first late-night milestone", "kind": "anniversary"}
        ],
    )
    monkeypatch.setattr(
        presence_context.db,
        "list_sessions",
        lambda database_url, limit=None, completed_only=False: [
            {"started_at": "2025-03-20T20:30:00+00:00"}
        ],
    )

    context = presence_context.build_presence_context(settings.database_url, settings, now=fixed_now)

    assert context["days_since_last_chat"] == 0
    assert context["stress_signal_dates"] == ["2026-03-18T12:00:00+00:00"]
    assert "first late-night milestone" in context["milestones_today"]
    assert "relationship anniversary" in context["milestones_today"]
