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
    fallback_used: bool
    error: str | None = None


class LLMClient:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.settings = settings
        self.soul = soul
        self._anthropic = None
        self._openai = None

        if settings.anthropic_api_key:
            try:
                from anthropic import Anthropic

                self._anthropic = Anthropic(api_key=settings.anthropic_api_key)
            except Exception:
                self._anthropic = None

        if settings.openai_api_key:
            try:
                from openai import OpenAI

                self._openai = OpenAI(api_key=settings.openai_api_key)
            except Exception:
                self._openai = None

    def reply(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        mood: MoodSnapshot,
        stream_handler: StreamHandler | None = None,
    ) -> LLMResult:
        errors: list[str] = []

        if self._anthropic is not None:
            try:
                return self._reply_anthropic(system_prompt, messages, stream_handler)
            except Exception as exc:
                errors.append(f"anthropic: {exc}")

        if self._openai is not None:
            try:
                return self._reply_openai(system_prompt, messages, stream_handler)
            except Exception as exc:
                errors.append(f"openai: {exc}")

        fallback_text = self._offline_reply(messages[-1]["content"], mood)
        self._emit(stream_handler, fallback_text)
        return LLMResult(
            text=fallback_text,
            provider="offline",
            model="heuristic-companion",
            fallback_used=True,
            error=" | ".join(errors) if errors else None,
        )

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

    def _reply_anthropic(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        stream_handler: StreamHandler | None,
    ) -> LLMResult:
        chunks: list[str] = []
        with self._anthropic.messages.stream(
            model=self.settings.llm_model,
            max_tokens=self.settings.llm_max_tokens,
            temperature=0.8,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)
                self._emit(stream_handler, text)
        return LLMResult(
            text="".join(chunks).strip(),
            provider="anthropic",
            model=self.settings.llm_model,
            fallback_used=False,
        )

    def _reply_openai(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        stream_handler: StreamHandler | None,
    ) -> LLMResult:
        chunks: list[str] = []
        stream = self._openai.chat.completions.create(
            model=self.settings.fallback_llm_model,
            temperature=0.8,
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
            model=self.settings.fallback_llm_model,
            fallback_used=False,
        )

    def _offline_reply(self, user_input: str, mood: MoodSnapshot) -> str:
        lowered = user_input.strip().rstrip("?!.")
        if mood.companion_state == "warm":
            return f"That sounds rough. I'm here with you. What part of \"{lowered}\" hit the hardest?"
        if mood.companion_state == "quiet":
            return "That sounds like a lot. We can keep this small. Do you want to put one piece of it into words?"
        if mood.companion_state == "concerned":
            return "I can hear the pressure in that. What feels most urgent right now, and what feels merely loud?"
        if mood.companion_state == "playful":
            return f"That has good energy. Tell me the full story behind \"{lowered}\"."
        if mood.companion_state == "reflective":
            return "That has a late-night kind of gravity to it. What are you circling around beneath the surface?"
        return f"I'm listening. Say a little more about \"{lowered}\"."

    def _emit(self, stream_handler: StreamHandler | None, text: str) -> None:
        if stream_handler is not None:
            stream_handler(text)
