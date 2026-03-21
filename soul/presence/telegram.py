from __future__ import annotations

import json
import socket
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from soul import db
from soul.config import Settings, get_settings
from soul.presence.runtime import PresenceRuntime, PresenceTurnResult


JsonDict = dict[str, object]
_HTTP_TIMEOUT_SECONDS: int = 15
_LONGPOLL_TIMEOUT_SECONDS: int = 20


@dataclass(slots=True)
class TelegramUpdate:
    update_id: int
    chat_id: int
    text: str
    user_id: int | None = None
    username: str | None = None
    first_name: str | None = None


@dataclass(slots=True)
class TelegramSendResult:
    ok: bool
    chat_id: int | None
    message: str
    error: str | None = None


class TelegramClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = "https://api.telegram.org",
        opener: Callable[..., object] | None = None,
        timeout: int = _HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.token = token or ""
        self.base_url = base_url.rstrip("/")
        self._open = opener or urlopen
        # _timeout applies to _post/send_message; get_updates computes its own long-poll timeout.
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    @property
    def api_root(self) -> str:
        return f"{self.base_url}/bot{self.token}"

    def status(self) -> str:
        return "enabled" if self.enabled else "disabled: missing bot token"

    def send_message(self, chat_id: int, text: str, *, parse_mode: str | None = None) -> TelegramSendResult:
        if not self.enabled:
            return TelegramSendResult(ok=False, chat_id=chat_id, message=text, error="missing bot token")

        payload: JsonDict = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            response = self._post("sendMessage", payload)
            if not response.get("ok"):
                description = response.get("description")
                error_code = response.get("error_code")
                error = description or error_code or "telegram api error"
                return TelegramSendResult(ok=False, chat_id=chat_id, message=text, error=f"telegram_error: {error}")
            return TelegramSendResult(ok=True, chat_id=chat_id, message=text)
        except URLError as exc:
            return TelegramSendResult(ok=False, chat_id=chat_id, message=text, error=f"telegram_error: {exc.reason}")
        except Exception as exc:
            return TelegramSendResult(ok=False, chat_id=chat_id, message=text, error=f"unexpected: {exc}")

    def get_updates(self, *, offset: int | None = None, timeout: int = 10) -> list[JsonDict]:
        if not self.enabled:
            return []

        params: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        request = Request(f"{self.api_root}/getUpdates?{urlencode(params)}", method="GET")
        http_timeout = min(timeout + _LONGPOLL_TIMEOUT_SECONDS, 60)
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(http_timeout)
        try:
            with self._open(request, http_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, TimeoutError) as exc:
            warnings.warn(f"Telegram get_updates timed out or failed: {exc}", stacklevel=2)
            return []
        finally:
            socket.setdefaulttimeout(previous_timeout)
        return list(payload.get("result", []))

    def _post(self, method: str, payload: JsonDict) -> JsonDict:
        request = Request(
            f"{self.api_root}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._open(request, self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            description = payload.get("description")
            error_code = payload.get("error_code")
            raise URLError(description or error_code or "telegram api error")
        return payload


class TelegramBotRunner:
    def __init__(
        self,
        runtime: PresenceRuntime | None = None,
        telegram_client: TelegramClient | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.runtime = runtime or PresenceRuntime(self.settings)
        token = self.settings.telegram_bot_token.get_secret_value() if self.settings.telegram_bot_token else None
        self.telegram = telegram_client or TelegramClient(token)

    def status(self) -> dict[str, str]:
        allowed_chat_id = self._configured_chat_id()
        if not self.telegram.enabled:
            telegram_state = self.telegram.status()
        elif allowed_chat_id is None:
            telegram_state = "disabled: missing valid TELEGRAM_CHAT_ID"
        else:
            telegram_state = "enabled"
        return {
            "telegram": telegram_state,
            "presence": "ready" if self.runtime else "disabled",
            "allowed_chat": str(allowed_chat_id) if allowed_chat_id is not None else "unset",
        }

    def handle_update(self, update: TelegramUpdate) -> PresenceTurnResult | TelegramSendResult:
        allowed_chat_id = self._configured_chat_id()
        if not self.telegram.enabled or allowed_chat_id is None:
            return TelegramSendResult(ok=False, chat_id=update.chat_id, message=update.text, error="telegram disabled")
        if update.chat_id != allowed_chat_id:
            return TelegramSendResult(ok=False, chat_id=update.chat_id, message=update.text, error="unauthorized chat")

        session_id = f"telegram-{update.chat_id}-{datetime.now(timezone.utc).date().isoformat()}"
        db.close_open_sessions_with_prefix(
            self.settings.database_url,
            f"telegram-{update.chat_id}-",
            except_session_id=session_id,
        )

        result = self.runtime.handle_text(
            update.text,
            session_id=session_id,
            user_label=update.username or update.first_name or f"telegram-{update.chat_id}",
            close_session=False,
            export_session_end=True,
        )
        return self.telegram.send_message(update.chat_id, result.reply_text)

    def _configured_chat_id(self) -> int | None:
        raw_chat_id = str(self.settings.telegram_chat_id or "").strip()
        if not raw_chat_id:
            return None
        try:
            return int(raw_chat_id)
        except ValueError:
            return None

    def poll_once(self, *, offset: int | None = None, timeout: int = 10) -> int:
        processed = 0
        for raw_update in self.telegram.get_updates(offset=offset, timeout=timeout):
            update = self._parse_update(raw_update)
            if update is None:
                continue
            self.handle_update(update)
            processed += 1
        return processed

    def run_forever(self, *, poll_interval: float = 1.0) -> None:
        import time

        offset: int | None = None
        while True:
            try:
                updates = self.telegram.get_updates(offset=offset, timeout=10)
            except Exception as exc:
                warnings.warn(f"Telegram polling failed: {exc}", stacklevel=2)
                time.sleep(poll_interval)
                continue
            for raw_update in updates:
                try:
                    update = self._parse_update(raw_update)
                    if update is None:
                        continue
                    offset = max(offset or 0, update.update_id + 1)
                    self.handle_update(update)
                except Exception as exc:
                    warnings.warn(f"Telegram update handling failed: {exc}", stacklevel=2)
            time.sleep(poll_interval)

    def _parse_update(self, raw: JsonDict) -> TelegramUpdate | None:
        return parse_update_payload(raw)


def iter_updates(client: TelegramClient, *, offset: int | None = None, timeout: int = 10) -> Iterable[TelegramUpdate]:
    for raw in client.get_updates(offset=offset, timeout=timeout):
        update = parse_update_payload(raw)
        if update is not None:
            yield update


def parse_update_payload(raw: JsonDict) -> TelegramUpdate | None:
    update_id = raw.get("update_id")
    message = raw.get("message")
    if not isinstance(update_id, int) or not isinstance(message, dict):
        return None

    chat = message.get("chat")
    text = message.get("text")
    if not isinstance(chat, dict) or not isinstance(text, str):
        return None

    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return None

    from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
    user_id = from_user.get("id") if isinstance(from_user, dict) and isinstance(from_user.get("id"), int) else None
    username = from_user.get("username") if isinstance(from_user, dict) and isinstance(from_user.get("username"), str) else None
    first_name = from_user.get("first_name") if isinstance(from_user, dict) and isinstance(from_user.get("first_name"), str) else None

    return TelegramUpdate(
        update_id=update_id,
        chat_id=chat_id,
        text=text,
        user_id=user_id,
        username=username,
        first_name=first_name,
    )
