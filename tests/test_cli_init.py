from __future__ import annotations

import os
import stat

from typer.testing import CliRunner

from soul import config
from soul import cli
from soul.config import Settings


def _confirm_responder(mapping: dict[str, bool]):
    def fake_confirm(cls, prompt, default=False):  # noqa: ANN001, ANN202
        del default
        normalized = str(prompt).casefold()
        for needle, response in mapping.items():
            if needle in normalized:
                return response
        raise AssertionError(f"Unexpected confirm prompt: {prompt}")

    return classmethod(fake_confirm)


def test_init_writes_env_and_bootstraps_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        cli,
        "_prompt_text",
        lambda label, *, default=None, required=False: {  # noqa: ARG005
            "OpenAI-compatible base URL (optional)": "",
            "Chat model": "gpt-4.1-mini",
            "Mood model": "gpt-4.1-mini",
            "SOUL data directory": "./custom_soul_data",
        }.get(label, default or ""),
    )
    monkeypatch.setattr(
        cli,
        "_prompt_secret",
        lambda label, *, existing=None, required=False: {  # noqa: ARG005
            "OpenAI API key": "sk-test-init",
        }[label],
    )
    monkeypatch.setattr(cli, "_prompt_timezone", lambda default: "UTC")
    monkeypatch.setattr(
        cli.Confirm,
        "ask",
        _confirm_responder(
            {
                "enable voice support": False,
                "enable telegram bot support": False,
            }
        ),
    )

    env_file = tmp_path / ".env"
    result = CliRunner().invoke(cli.app, ["init", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert env_file.exists()
    assert 'OPENAI_API_KEY="sk-test-init"' in env_file.read_text(encoding="utf-8")
    assert 'LLM_MODEL="gpt-4.1-mini"' in env_file.read_text(encoding="utf-8")
    assert "ENABLE_VOICE=false" in env_file.read_text(encoding="utf-8")
    assert "ENABLE_TELEGRAM=false" in env_file.read_text(encoding="utf-8")

    settings = Settings(_env_file=str(env_file))
    assert settings.soul_data_dir == tmp_path / "custom_soul_data"
    assert settings.soul_file.exists()
    assert settings.sqlite_path.exists()

    if os.name != "nt":
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_init_writes_optional_voice_and_telegram_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        cli,
        "_prompt_text",
        lambda label, *, default=None, required=False: {  # noqa: ARG005
            "OpenAI-compatible base URL (optional)": "https://example.test/v1",
            "Chat model": "provider/chat-model",
            "Mood model": "provider/mood-model",
            "SOUL data directory": "./wizard_data",
            "ElevenLabs voice ID": "voice_123",
        }.get(label, default or ""),
    )
    monkeypatch.setattr(
        cli,
        "_prompt_secret",
        lambda label, *, existing=None, required=False: {  # noqa: ARG005
            "OpenAI API key": "sk-test-optional",
            "ElevenLabs API key": "el-test-key",
            "Telegram bot token": "123456:telegram-token",
        }[label],
    )
    monkeypatch.setattr(cli, "_prompt_timezone", lambda default: "Asia/Kolkata")
    monkeypatch.setattr(cli, "_prompt_int", lambda label, *, default=None: "123456789")
    monkeypatch.setattr(
        cli.Confirm,
        "ask",
        _confirm_responder(
            {
                "enable voice support": True,
                "enable telegram bot support": True,
            }
        ),
    )

    env_file = tmp_path / ".env"
    result = CliRunner().invoke(cli.app, ["init", "--env-file", str(env_file)])

    assert result.exit_code == 0
    content = env_file.read_text(encoding="utf-8")
    assert 'OPENAI_BASE_URL="https://example.test/v1"' in content
    assert "ENABLE_VOICE=true" in content
    assert 'ELEVENLABS_API_KEY="el-test-key"' in content
    assert 'ELEVENLABS_VOICE_ID="voice_123"' in content
    assert "ENABLE_TELEGRAM=true" in content
    assert 'TELEGRAM_BOT_TOKEN="123456:telegram-token"' in content
    assert 'TELEGRAM_CHAT_ID="123456789"' in content

    settings = Settings(_env_file=str(env_file))
    assert settings.enable_voice is True
    assert settings.enable_telegram is True
    assert settings.elevenlabs_voice_id == "voice_123"
    assert settings.telegram_chat_id == "123456789"


def test_init_does_not_overwrite_existing_env_when_declined(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text('OPENAI_API_KEY="keep-me"\n', encoding="utf-8")

    monkeypatch.setattr(
        cli.Confirm,
        "ask",
        _confirm_responder(
            {
                "already exists": False,
            }
        ),
    )
    monkeypatch.setattr(cli, "_prompt_text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompt should not run")))
    monkeypatch.setattr(cli, "_prompt_secret", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompt should not run")))

    result = CliRunner().invoke(cli.app, ["init", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert env_file.read_text(encoding="utf-8") == 'OPENAI_API_KEY="keep-me"\n'
    assert "Cancelled" in result.stdout
