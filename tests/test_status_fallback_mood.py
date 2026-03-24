from __future__ import annotations

from typer.testing import CliRunner

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul
from soul.maintenance.proactive import ReachOutCandidate
import soul.cli as cli


def test_status_falls_back_to_last_companion_state_when_no_current_mood(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        _env_file=None,
    )
    db.init_db(settings.database_url)
    session_id = db.create_session(settings.database_url, "Ara")
    db.log_message(
        settings.database_url,
        session_id=session_id,
        role="assistant",
        content="I am here with you.",
        companion_state="concerned",
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, Soul(raw={}, name="Ara", voice="warm", energy="steady")))
    monkeypatch.setattr(cli.MoodEngine, "current_state", lambda self, user_id=None: None)
    monkeypatch.setattr(cli, "refresh_proactive_candidates", lambda settings, channel="cli": [])

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "concerned" in result.stdout


def test_status_uses_fresh_reach_out_candidates(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        _env_file=None,
    )
    db.init_db(settings.database_url)

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, Soul(raw={}, name="Ara", voice="warm", energy="steady")))
    monkeypatch.setattr(cli.MoodEngine, "current_state", lambda self, user_id=None: None)
    monkeypatch.setattr(
        cli,
        "refresh_proactive_candidates",
        lambda settings, channel="cli": [
            ReachOutCandidate(trigger="silence_3_days", message="checking in"),
            ReachOutCandidate(trigger="monday_morning", message="monday"),
        ],
    )

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "Reach-out candidates" in result.stdout
    assert "2" in result.stdout
