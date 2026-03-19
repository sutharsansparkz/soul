from __future__ import annotations

from types import SimpleNamespace

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

    def opener(request):
        captured["url"] = request.full_url
        captured["data"] = request.data
        return Response(b'{"ok": true, "result": true}')

    client = TelegramClient(token="abc123", opener=opener)

    result = client.send_message(42, "hello", parse_mode="Markdown")

    assert result.ok is True
    assert captured["url"].endswith("/sendMessage")
    assert b'"chat_id": 42' in captured["data"]
    assert b'"parse_mode": "Markdown"' in captured["data"]


def test_bot_runner_parses_updates():
    runner = TelegramBotRunner(
        runtime=SimpleNamespace(handle_text=lambda *args, **kwargs: SimpleNamespace(reply_text="hi")),
        telegram_client=TelegramClient(token="abc123", opener=lambda request: None),
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
