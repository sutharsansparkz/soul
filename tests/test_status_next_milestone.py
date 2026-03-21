from __future__ import annotations

from datetime import datetime, timezone

from soul.config import Settings
import soul.cli as cli


def test_next_milestone_label_prefers_active_streak_countdown(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        timezone_name="UTC",
    )
    now = datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc)
    sessions = [
        {"started_at": "2026-03-16T12:00:00+00:00"},
        {"started_at": "2026-03-17T12:00:00+00:00"},
        {"started_at": "2026-03-18T12:00:00+00:00"},
        {"started_at": "2026-03-19T12:00:00+00:00"},
        {"started_at": "2026-03-20T12:00:00+00:00"},
        {"started_at": "2026-03-21T12:00:00+00:00"},
    ]

    monkeypatch.setattr(cli.db, "list_sessions", lambda database_url, limit=None, completed_only=False: sessions[:limit] if limit else sessions)
    monkeypatch.setattr(cli.db, "milestone_exists", lambda database_url, kind: False)

    label = cli._next_milestone_label(settings, total_messages=10, now=now)

    assert label == "7-day conversation streak (1 day away)"


def test_next_milestone_label_surfaces_nearest_anniversary(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        timezone_name="UTC",
    )
    now = datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc)
    sessions = [{"started_at": "2026-02-20T12:00:00+00:00"}]

    monkeypatch.setattr(cli.db, "list_sessions", lambda database_url, limit=None, completed_only=False: sessions[:limit] if limit else sessions)
    monkeypatch.setattr(cli.db, "milestone_exists", lambda database_url, kind: False)

    label = cli._next_milestone_label(settings, total_messages=95, now=now)

    assert label == "1-month anniversary (1 day away)"
