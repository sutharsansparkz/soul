from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul


StreamHandler = Callable[[str], None]


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

            # base_url lets any OpenAI-compatible endpoint be used
            # (e.g. Ollama, LM Studio, Together AI, Azure OpenAI, etc.)
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
        return self._reply_openai(system_prompt, messages, stream_handler)

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
