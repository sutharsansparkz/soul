from __future__ import annotations

from datetime import datetime, timezone

from soul import db
from soul.config import Settings
from soul.maintenance.consolidation import StructuredSessionInsights, consolidate_pending_sessions
from soul.maintenance.proactive import ReachOutCandidate, dispatch_reach_out_candidates


def test_consolidate_pending_sessions_processes_all_completed_sessions_once(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)
    monkeypatch.setattr(
        "soul.maintenance.consolidation._extract_structured_insights",
        lambda user_lines, settings: StructuredSessionInsights(),  # noqa: ARG005
    )

    first = db.create_session(database_url, "Ara")
    db.log_message(database_url, session_id=first, role="user", content="I had a rough day and felt invisible.")
    db.log_message(database_url, session_id=first, role="assistant", content="Tell me more.")
    db.close_session(database_url, first)

    second = db.create_session(database_url, "Ara")
    db.log_message(database_url, session_id=second, role="user", content="I launched the beta today and I am excited.")
    db.log_message(database_url, session_id=second, role="assistant", content="That has good energy.")
    db.close_session(database_url, second)

    settings = Settings(database_url=database_url, soul_data_path=str(tmp_path / "soul_data"), _env_file=None)
    results = consolidate_pending_sessions(database_url=database_url, settings=settings, source="test")
    rerun = consolidate_pending_sessions(database_url=database_url, settings=settings, source="test")

    assert len(results) == 2
    assert rerun == []


def test_dispatch_reach_out_candidates_dedupes_daily_delivery(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        telegram_bot_token="token",
        telegram_chat_id="12345",
        enable_telegram=True,
    )
    db.init_db(settings.database_url)

    sent_messages: list[tuple[int, str]] = []

    def fake_send_message(self, chat_id: int, text: str, parse_mode: str | None = None):  # noqa: ARG001
        sent_messages.append((chat_id, text))

        class Result:
            ok = True
            error = None

        return Result()

    monkeypatch.setattr("soul.maintenance.proactive.TelegramClient.send_message", fake_send_message)

    candidates = [ReachOutCandidate(trigger="silence_3_days", message="Checking in.")]
    first = dispatch_reach_out_candidates(settings, candidates, today=datetime(2026, 3, 19, tzinfo=timezone.utc))
    second = dispatch_reach_out_candidates(settings, candidates, today=datetime(2026, 3, 19, tzinfo=timezone.utc))

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert sent_messages == [(12345, "Checking in.")]
