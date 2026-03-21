from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from typing import Any

from soul.config import Settings

_LOCAL_STATE_CACHE: dict[str, dict] = {}


@dataclass(slots=True)
class MoodSnapshot:
    user_mood: str
    companion_state: str
    confidence: float
    rationale: str


class MoodEngine:
    """Mood detection via OpenAI and Redis-backed companion state."""

    STATE_MAP = {
        "overwhelmed": "quiet",
        "stressed": "concerned",
        "celebrating": "playful",
        "curious": "curious",
        "reflective": "reflective",
        "venting": "warm",
        "neutral": "neutral",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def analyze(self, text: str, user_id: str | None = None, now: datetime | None = None) -> MoodSnapshot:
        now = now or datetime.now(timezone.utc)
        user_id = user_id or self.settings.user_id

        user_mood, confidence, rationale = self._openai_mood(text)

        previous_state = self.current_state(user_id)
        if user_mood == "neutral" and not self._should_preserve_previous_state(text):
            previous_state = None
        companion_state = self._select_companion_state(user_mood, previous_state, now)
        self._persist_state(
            user_id=user_id,
            payload={
                "state": companion_state,
                "last_user_mood": user_mood,
                "updated_at": now.isoformat(),
            },
        )
        return MoodSnapshot(
            user_mood=user_mood,
            companion_state=companion_state,
            confidence=confidence,
            rationale=rationale,
        )

    def _openai_mood(self, text: str) -> tuple[str, float, str]:
        if not self.settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for mood classification. "
                "Set it in your .env file."
            )

        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.openai_api_key.get_secret_value(),
            base_url=self.settings.openai_base_url or None,
        )
        valid = self.settings.mood_valid_labels
        labels_str = ", ".join(valid)
        prompt = (
            "Classify the emotional mood of the following user message.\n"
            'Return JSON only: {"mood": "<label>", "confidence": <0.0-1.0>}\n'
            f"Valid mood labels: {labels_str}\n"
            f'Message: "{text}"'
        )

        response = client.chat.completions.create(
            model=self.settings.mood_openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.settings.mood_openai_max_tokens,
            temperature=self.settings.mood_openai_temperature,
        )
        raw = (response.choices[0].message.content or "").strip()
        payload = json.loads(raw)
        mood = str(payload.get("mood", "")).casefold()

        if mood not in self.STATE_MAP:
            raise ValueError(
                f"OpenAI returned unrecognised mood label {mood!r}. "
                f"Expected one of: {labels_str}"
            )
        confidence = float(payload.get("confidence", 0.8))

        return mood, confidence, f"openai mood prompt (model={self.settings.mood_openai_model})"

    def _should_preserve_previous_state(self, text: str) -> bool:
        return len(text.split()) <= 4

    def current_state(self, user_id: str | None = None) -> dict[str, Any] | None:
        user_id = user_id or self.settings.user_id
        raw: str | None = None
        if self.redis_client is not None:
            try:
                raw = self.redis_client.get(self._redis_key(user_id))
            except Exception:
                raw = None
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        cached = _LOCAL_STATE_CACHE.get(user_id)
        return dict(cached) if cached is not None else None

    def _select_companion_state(
        self,
        user_mood: str,
        previous_state: dict[str, Any] | None,
        now: datetime,
    ) -> str:
        if user_mood != "neutral":
            return self.STATE_MAP[user_mood]

        if previous_state:
            updated_at = previous_state.get("updated_at")
            try:
                previous_dt = datetime.fromisoformat(updated_at)
            except (TypeError, ValueError):
                previous_dt = None
            if previous_dt is not None:
                hours = (now - previous_dt).total_seconds() / 3600
                if hours < self.settings.mood_decay_hours:
                    return str(previous_state.get("state") or "neutral")

        return "neutral"

    def _persist_state(self, *, user_id: str, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=True)
        if self.redis_client is not None:
            try:
                self.redis_client.set(self._redis_key(user_id), serialized)
            except Exception:
                _LOCAL_STATE_CACHE[user_id] = dict(payload)
                return
        _LOCAL_STATE_CACHE[user_id] = dict(payload)

    def _redis_key(self, user_id: str) -> str:
        return f"{self.settings.redis_key_prefix}:mood:{user_id}"

    @cached_property
    def redis_client(self):  # type: ignore[no-untyped-def]
        try:
            import redis
        except ImportError:
            return None

        try:
            return redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
        except Exception:
            return None
