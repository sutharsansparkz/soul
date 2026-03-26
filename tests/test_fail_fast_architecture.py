from __future__ import annotations

import pytest

import soul.cli as cli
from soul.bootstrap import FeatureInitializationError, StartupDependencyError, TurnExecutionError, validate_startup
from soul.config import Settings
from soul.core.soul_loader import Soul
from soul.observability.traces import TurnTraceRepository
from typer.testing import CliRunner


def _settings(tmp_path, **overrides):
    values = {
        "database_url": f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        "soul_data_path": str(tmp_path / "soul_data"),
        "openai_api_key": "test-key",
        "_env_file": None,
        "enable_proactive": False,
        "enable_reflection": False,
        "enable_drift": False,
        "enable_background_jobs": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_validate_startup_fails_when_voice_feature_is_enabled_without_credentials(tmp_path):
    settings = _settings(tmp_path, enable_voice=True)

    with pytest.raises(FeatureInitializationError, match="ENABLE_VOICE is true"):
        validate_startup(settings)


def test_validate_startup_blocks_pending_legacy_state(tmp_path):
    settings = _settings(tmp_path)
    legacy_file = settings.soul_data_dir / "user_story.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text('{"basics":{"name":"Casey"}}\n', encoding="utf-8")

    with pytest.raises(StartupDependencyError, match="user_story.json"):
        validate_startup(settings)


def test_chat_rejects_voice_when_feature_flag_is_disabled(tmp_path, monkeypatch):
    settings = _settings(tmp_path, enable_voice=False)
    soul = Soul(raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}}, name="Ara", voice="warm", energy="steady")
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))

    result = CliRunner().invoke(cli.app, ["chat", "--voice"])

    assert result.exit_code == 1
    assert "ENABLE_VOICE=true" in result.stdout


def test_debug_last_turn_reads_sqlite_trace(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    soul = Soul(raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}}, name="Ara", voice="warm", energy="steady")
    cli._ensure_runtime_files(settings)
    from soul.persistence.sqlite_setup import ensure_schema
    from soul.memory.repositories.messages import MessagesRepository

    ensure_schema(settings.database_url)
    # Create a real session so the user-scoped trace query can join through it
    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    session_id = messages_repo.create_session("Ara")
    TurnTraceRepository(settings.database_url).write_trace(
        session_id=session_id,
        input_message_id="user-1",
        reply_message_id="assistant-1",
        payload={"provider": "local-runtime", "model": "runtime-clock"},
    )
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))

    result = CliRunner().invoke(cli.app, ["debug", "last-turn"])

    assert result.exit_code == 0
    assert "runtime-clock" in result.stdout


def test_db_init_command_is_idempotent(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    first = CliRunner().invoke(cli.app, ["db", "init"])
    second = CliRunner().invoke(cli.app, ["db", "init"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Initialized database" in second.stdout


def test_run_jobs_reports_error_without_traceback(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    soul = Soul(raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}}, name="Ara", voice="warm", energy="steady")
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul))
    monkeypatch.setattr(cli, "run_enabled_maintenance", lambda settings: (_ for _ in ()).throw(RuntimeError("Connection error.")))

    result = CliRunner().invoke(cli.app, ["run-jobs"])

    assert result.exit_code == 1
    assert "Maintenance run failed." in result.stdout
    assert "Connection error." in result.stdout


def test_telegram_bot_reports_poll_failure_without_traceback(tmp_path, monkeypatch):
    settings = _settings(
        tmp_path,
        enable_telegram=True,
        telegram_bot_token="dummy-token",
        telegram_chat_id="12345",
    )

    class FakeRunner:
        def __init__(self, settings):  # noqa: ANN001
            self.settings = settings

        def status(self):
            return {"telegram": "enabled", "presence": "ready", "allowed_chat": "12345"}

        def run_forever(self):
            raise RuntimeError("Telegram get_updates failed: Connection error.")

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "TelegramBotRunner", FakeRunner)

    result = CliRunner().invoke(cli.app, ["telegram-bot"])

    assert result.exit_code == 1
    assert "Telegram bot stopped." in result.stdout
    assert "Telegram get_updates failed: Connection error." in result.stdout
