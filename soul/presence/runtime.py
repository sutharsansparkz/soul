from __future__ import annotations

from dataclasses import dataclass, field

from soul import db
from soul.config import Settings, get_settings
from soul.core.context_builder import ContextBuilder
from soul.core.llm_client import LLMClient
from soul.core.mood_engine import MoodEngine
from soul.core.post_processor import PostProcessor
from soul.core.soul_loader import Soul, load_soul


@dataclass(slots=True)
class PresenceTurnResult:
    session_id: str
    user_text: str
    reply_text: str
    provider: str
    model: str
    fallback_used: bool
    metadata: dict[str, object] = field(default_factory=dict)


class PresenceRuntime:
    """Bridge optional presence surfaces to the existing core runtime."""

    def __init__(self, settings: Settings | None = None, soul: Soul | None = None) -> None:
        self.settings = settings or get_settings()
        db.init_db(self.settings.database_url)
        self.soul = soul or load_soul(self.settings.soul_file)
        self.mood_engine = MoodEngine(self.settings)
        self.builder = ContextBuilder(self.settings, self.soul)
        self.client = LLMClient(self.settings, self.soul)
        self.post_processor = PostProcessor(self.settings)

    def handle_text(
        self,
        user_text: str,
        *,
        session_id: str | None = None,
        user_label: str | None = None,
    ) -> PresenceTurnResult:
        active_session_id = session_id or db.create_session(self.settings.database_url, self.soul.name)
        if session_id and not db.session_exists(self.settings.database_url, session_id):
            db.create_session(self.settings.database_url, self.soul.name, session_id=session_id)
        try:
            mood = self.mood_engine.analyze(user_text, user_id=user_label or self.settings.user_id)
            db.log_message(
                self.settings.database_url,
                session_id=active_session_id,
                role="user",
                content=user_text,
                user_mood=mood.user_mood,
                companion_state=mood.companion_state,
                provider="presence",
                metadata={"confidence": mood.confidence, "rationale": mood.rationale},
            )

            bundle = self.builder.build(session_id=active_session_id, user_input=user_text, mood=mood)
            result = self.client.reply(system_prompt=bundle.system_prompt, messages=bundle.messages, mood=mood)
            db.log_message(
                self.settings.database_url,
                session_id=active_session_id,
                role="assistant",
                content=result.text,
                user_mood=mood.user_mood,
                companion_state=mood.companion_state,
                provider=result.provider,
                metadata={"model": result.model, "fallback_used": result.fallback_used, "error": result.error},
            )
            self.post_processor.process_turn(
                session_id=active_session_id,
                user_text=user_text,
                assistant_text=result.text,
                mood=mood,
            )
            return PresenceTurnResult(
                session_id=active_session_id,
                user_text=user_text,
                reply_text=result.text,
                provider=result.provider,
                model=result.model,
                fallback_used=result.fallback_used,
                metadata={"companion_state": mood.companion_state, "user_mood": mood.user_mood},
            )
        finally:
            db.close_session(self.settings.database_url, active_session_id)
