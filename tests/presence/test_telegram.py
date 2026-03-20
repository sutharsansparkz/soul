from __future__ import annotations

import socket
from types import SimpleNamespace
from urllib.error import URLError

from soul.config import Settings
from soul.presence.telegram import TelegramBotRunner, TelegramClient, TelegramUpdate


def test_disabled_telegram_client_degrades_cleanly():
    client = TelegramClient(token="")

    result = client.send_message(123, "hello")

    assert result.ok is False
    assert result.error == "missing bot token"
    assert client.get_updates() == []


def test_telegram_client_uses_payload_and_opener():
    captured = {}

    class Response:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body

    def opener(request, timeout=None):
        captured["url"] = request.full_url
        captured["data"] = request.data
        return Response(b'{"ok": true, "result": true}')

    client = TelegramClient(token="abc123", opener=opener)

    result = client.send_message(42, "hello", parse_mode="Markdown")

    assert result.ok is True
    assert captured["url"].endswith("/sendMessage")
    assert b'"chat_id": 42' in captured["data"]
    assert b'"parse_mode": "Markdown"' in captured["data"]


def test_telegram_client_returns_not_ok_when_api_returns_ok_false():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": false, "error_code": 400, "description": "Bad Request"}'

    def opener(request, timeout=None):  # noqa: ARG001
        return Response()

    client = TelegramClient(token="abc123", opener=opener)

    result = client.send_message(42, "hello")

    assert result.ok is False


def test_bot_runner_parses_updates():
    runner = TelegramBotRunner(
        runtime=SimpleNamespace(handle_text=lambda *args, **kwargs: SimpleNamespace(reply_text="hi")),
        telegram_client=TelegramClient(token="abc123", opener=lambda request, timeout=None: None),
    )

    update = runner._parse_update(
        {
            "update_id": 7,
            "message": {
                "chat": {"id": 99},
                "text": "hey",
                "from": {"id": 1, "username": "user", "first_name": "User"},
            },
        }
    )

    assert isinstance(update, TelegramUpdate)
    assert update.chat_id == 99
    assert update.text == "hey"


def test_bot_runner_requires_single_allowed_chat(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        telegram_bot_token="abc123",
        telegram_chat_id="42",
    )
    called = {"count": 0}
    runner = TelegramBotRunner(
        runtime=SimpleNamespace(handle_text=lambda *args, **kwargs: called.__setitem__("count", called["count"] + 1)),
        telegram_client=TelegramClient(token="abc123", opener=lambda request, timeout=None: None),
        settings=settings,
    )

    rejected = runner.handle_update(TelegramUpdate(update_id=1, chat_id=99, text="hey"))

    assert rejected.ok is False
    assert rejected.error == "unauthorized chat"
    assert called["count"] == 0


def test_bot_runner_status_requires_valid_chat_id(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        telegram_bot_token="abc123",
        telegram_chat_id="",
    )
    runner = TelegramBotRunner(
        runtime=SimpleNamespace(handle_text=lambda *args, **kwargs: SimpleNamespace(reply_text="hi")),
        telegram_client=TelegramClient(token="abc123", opener=lambda request, timeout=None: None),
        settings=settings,
    )

    status = runner.status()

    assert status["telegram"].startswith("disabled")
    assert status["allowed_chat"] == "unset"


def test_telegram_client_raises_urlerror_on_timeout():
    def timeout_opener(request, timeout=None):  # noqa: ARG001
        raise URLError(socket.timeout("timed out"))

    client = TelegramClient(token="abc123", opener=timeout_opener, timeout=5)
    result = client.send_message(42, "hello")

    assert result.ok is False
    assert result.error is not None
