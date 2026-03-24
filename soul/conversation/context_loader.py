"""Context loading wrapper around the prompt context builder."""

from __future__ import annotations

from soul.config import Settings
from soul.core.context_builder import ContextBuilder, ContextBundle
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul


class ContextLoader:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.builder = ContextBuilder(settings, soul)

    def load(self, *, session_id: str, user_input: str, mood: MoodSnapshot) -> ContextBundle:
        return self.builder.build(session_id=session_id, user_input=user_input, mood=mood)
