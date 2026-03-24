from __future__ import annotations

from dataclasses import dataclass, field

from soul.config import Settings, get_settings
from soul.conversation.orchestrator import ConversationOrchestrator
from soul.core.soul_loader import Soul, load_soul
from soul.memory.repositories.messages import MessagesRepository


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
    """Bridge optional presence surfaces to the core conversation runtime."""

    def __init__(self, settings: Settings | None = None, soul: Soul | None = None) -> None:
        self.settings = settings or get_settings()
        self.soul = soul or load_soul(self.settings.soul_file)
        self.messages = MessagesRepository(self.settings.database_url, user_id=self.settings.user_id)
        self.orchestrator = ConversationOrchestrator(self.settings, self.soul)
        self.mood_engine = self.orchestrator.mood_engine
        self.client = self.orchestrator.client
        self.post_processor = self.orchestrator.post_processor
        self.traces = self.orchestrator.traces

    def handle_text(
        self,
        user_text: str,
        *,
        session_id: str | None = None,
        user_label: str | None = None,  # retained for compatibility
        close_session: bool = True,
        export_session_end: bool | None = None,
    ) -> PresenceTurnResult:
        del user_label
        should_export_session = close_session if export_session_end is None else export_session_end
        active_session_id = session_id or self.messages.create_session(self.soul.name)
        if session_id and not self.messages.session_exists(session_id):
            self.messages.create_session(self.soul.name, session_id=session_id)
        try:
            result = self.orchestrator.run_turn(session_id=active_session_id, user_text=user_text)
            return PresenceTurnResult(
                session_id=active_session_id,
                user_text=user_text,
                reply_text=result.llm_result.text,
                provider=result.llm_result.provider,
                model=result.llm_result.model,
                fallback_used=result.llm_result.fallback_used,
                metadata={
                    "companion_state": result.mood.companion_state,
                    "user_mood": result.mood.user_mood,
                    "trace_id": result.trace_id,
                },
            )
        finally:
            if close_session:
                self.messages.close_session(active_session_id)
            if should_export_session:
                self.orchestrator.post_processor.process_session_end(session_id=active_session_id)
