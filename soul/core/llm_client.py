from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul


StreamHandler = Callable[[str], None]

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class LLMResult:
    text: str
    provider: str
    model: str
    fallback_used: bool  # always False; retained for API compatibility
    error: str | None = None


class LLMClient:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.settings = settings
        self.soul = soul
        self._openai = None

        if settings.openai_api_key:
            from openai import OpenAI

            self._openai = OpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                base_url=settings.openai_base_url or None,
            )

    def reply(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        mood: MoodSnapshot,  # retained for API compatibility
        stream_handler: StreamHandler | None = None,
    ) -> LLMResult:
        if self._openai is None:
            raise RuntimeError("OPENAI_API_KEY is required. Set it in your .env file.")
        return self._reply_with_retry(system_prompt, messages, stream_handler)

    def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        stream_handler: StreamHandler | None = None,
    ) -> LLMResult:
        synthetic_mood = MoodSnapshot(
            user_mood="reflective",
            companion_state="reflective",
            confidence=1.0,
            rationale="job-mode prompt",
        )
        return self.reply(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            mood=synthetic_mood,
            stream_handler=stream_handler,
        )

    def _reply_with_retry(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        stream_handler: StreamHandler | None,
    ) -> LLMResult:
        last_error: Exception | None = None
        backoff = self.settings.llm_initial_backoff
        max_retries = self.settings.llm_max_retries

        for attempt in range(max_retries):
            try:
                return self._reply_openai(system_prompt, messages, stream_handler)
            except Exception as exc:
                last_error = exc
                if not self._is_retryable(exc):
                    raise
                if attempt < max_retries - 1:
                    logger.warning(
                        "LLM request failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        max_retries,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)
                    backoff *= self.settings.llm_backoff_multiplier

        raise last_error  # type: ignore[misc]

    def _is_retryable(self, exc: Exception) -> bool:
        """Check if the exception is a rate-limit or transient server error."""
        # openai library raises specific error types with status_code
        status_code = getattr(exc, "status_code", None)
        if status_code and int(status_code) in _RETRYABLE_STATUS_CODES:
            return True
        # Also retry on generic connection/timeout errors
        exc_name = type(exc).__name__
        if any(keyword in exc_name for keyword in ("Timeout", "Connection", "APIConnectionError")):
            return True
        return False

    def _reply_openai(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        stream_handler: StreamHandler | None,
    ) -> LLMResult:
        chunks: list[str] = []
        stream = self._openai.chat.completions.create(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            stream=True,
            messages=[{"role": "system", "content": system_prompt}, *messages],
        )
        for event in stream:
            delta = event.choices[0].delta.content or ""
            if not delta:
                continue
            chunks.append(delta)
            self._emit(stream_handler, delta)
        return LLMResult(
            text="".join(chunks).strip(),
            provider="openai",
            model=self.settings.llm_model,
            fallback_used=False,
        )

    def _emit(self, stream_handler: StreamHandler | None, text: str) -> None:
        if stream_handler is not None:
            stream_handler(text)
