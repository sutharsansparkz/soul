from __future__ import annotations

from typer.testing import CliRunner

from soul import db
from soul.config import Settings
from soul.core.soul_loader import Soul
from soul.tasks.proactive import ReachOutCandidate
from soul.memory.user_story import UserStory
import soul.cli as cli


def test_status_fallback_mood(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
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

    class FakeUserStoryRepository:
        def __init__(self, path):  # noqa: ANN001, ARG002
            pass

        def load(self):
            return UserStory()

    class FakeVoiceBridge:
        def __init__(self, settings):  # noqa: ANN001, ARG002
            pass

        def status(self):
            return {"voice": "disabled"}

    class FakeTelegramBotRunner:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ARG002
            pass

        def status(self):
            return {"telegram": "disabled", "presence": "ready", "allowed_chat": "unset"}

    monkeypatch.setattr(cli, "UserStoryRepository", FakeUserStoryRepository)
    monkeypatch.setattr(cli, "build_reach_out_candidates", lambda **kwargs: [])  # noqa: ARG005
    monkeypatch.setattr(cli, "save_reach_out_candidates", lambda *args, **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(cli, "VoiceBridge", FakeVoiceBridge)
    monkeypatch.setattr(cli, "TelegramBotRunner", FakeTelegramBotRunner)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "concerned" in result.stdout


def test_status_uses_fresh_reach_out_candidates_not_stale_file(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
    )
    db.init_db(settings.database_url)

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, Soul(raw={}, name="Ara", voice="warm", energy="steady")))
    monkeypatch.setattr(cli.MoodEngine, "current_state", lambda self, user_id=None: None)

    class FakeUserStoryRepository:
        def __init__(self, path):  # noqa: ANN001, ARG002
            pass

        def load(self):
            return UserStory()

    class FakeVoiceBridge:
        def __init__(self, settings):  # noqa: ANN001, ARG002
            pass

        def status(self):
            return {"voice": "disabled"}

    class FakeTelegramBotRunner:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ARG002
            pass

        def status(self):
            return {"telegram": "disabled", "presence": "ready", "allowed_chat": "unset"}

    monkeypatch.setattr(cli, "UserStoryRepository", FakeUserStoryRepository)
    monkeypatch.setattr(
        cli,
        "build_reach_out_candidates",
        lambda **kwargs: [
            ReachOutCandidate(trigger="silence_3_days", message="checking in"),
            ReachOutCandidate(trigger="monday_morning", message="monday"),
        ],
    )
    monkeypatch.setattr(
        cli,
        "load_reach_out_candidates",
        lambda path: (_ for _ in ()).throw(AssertionError("status should not load stale candidate files")),
    )
    monkeypatch.setattr(cli, "VoiceBridge", FakeVoiceBridge)
    monkeypatch.setattr(cli, "TelegramBotRunner", FakeTelegramBotRunner)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "Reach-out candidates" in result.stdout
    assert "2" in result.stdout
