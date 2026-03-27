"""Single-turn read/generate/write orchestration with tracing."""

from __future__ import annotations

import logging
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from time import perf_counter

from soul.bootstrap.errors import TurnExecutionError
from soul.config import Settings
from soul.conversation.context_loader import ContextLoader
from soul.core.llm_client import LLMClient, LLMResult
from soul.core.mood_engine import MoodEngine, MoodSnapshot
from soul.core.post_processor import PostProcessor
from soul.core.soul_loader import Soul
from soul.memory.repositories.messages import MessagesRepository
from soul.observability.traces import TurnTraceRepository

_logger = logging.getLogger(__name__)
_TRACE_POST_PROCESS_TIMEOUT_SECONDS = 0.25


@dataclass(slots=True)
class ConversationTurnResult:
    session_id: str
    user_message_id: str
    assistant_message_id: str
    mood: MoodSnapshot
    llm_result: LLMResult
    trace_id: str
    prompt_sections: list[str] = field(default_factory=list)
    post_process_future: Future[dict[str, object]] | None = None


class ConversationOrchestrator:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.settings = settings
        self.soul = soul
        self.messages = MessagesRepository(settings.database_url, user_id=settings.user_id)
        self.mood_engine = MoodEngine(settings)
        self.context_loader = ContextLoader(settings, soul)
        self.client = LLMClient(settings, soul)
        self.post_processor = PostProcessor(settings)
        self.traces = TurnTraceRepository(settings.database_url, user_id=settings.user_id)

    def run_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        stream_handler=None,  # type: ignore[no-untyped-def]
        before_generate=None,  # type: ignore[no-untyped-def]
    ) -> ConversationTurnResult:
        mood = self.mood_engine.analyze(user_text, user_id=self.settings.user_id, persist=False)
        user_message_id = self.messages.log_message(
            session_id=session_id,
            role="user",
            content=user_text,
            user_mood=mood.user_mood,
            companion_state=mood.companion_state,
            provider="local",
            metadata={
                "confidence": mood.confidence,
                "rationale": mood.rationale,
                "word_count": len(user_text.split()),
            },
        )
        self.mood_engine.repository.add_snapshot(
            session_id=session_id,
            message_id=user_message_id,
            user_mood=mood.user_mood,
            companion_state=mood.companion_state,
            confidence=mood.confidence,
            rationale=mood.rationale,
        )

        bundle = self.context_loader.load(session_id=session_id, user_input=user_text, mood=mood)
        if before_generate is not None:
            before_generate(mood, bundle)
        try:
            started = perf_counter()
            llm_result = self.client.reply(
                system_prompt=bundle.system_prompt,
                messages=bundle.messages,
                mood=mood,
                stream_handler=stream_handler,
            )
            latency_ms = round((perf_counter() - started) * 1000, 2)
            assistant_message_id = self.messages.log_message(
                session_id=session_id,
                role="assistant",
                content=llm_result.text,
                user_mood=mood.user_mood,
                companion_state=mood.companion_state,
                provider=llm_result.provider,
                metadata={"model": llm_result.model, "fallback_used": llm_result.fallback_used, "error": llm_result.error},
            )

            # Fire post-processing in a background thread so the user
            # doesn't wait for fact extraction / milestone updates.
            post_future = self.post_processor.process_turn_background(
                session_id=session_id,
                user_text=user_text,
                assistant_text=llm_result.text,
                mood=mood,
            )

            # Collect post-turn outputs for the trace.
            # We wait briefly (non-blocking check) but don't block the reply.
            post_turn: dict[str, object] = {}
            post_status = "complete"
            post_error: str | None = None
            try:
                post_turn = post_future.result(timeout=_TRACE_POST_PROCESS_TIMEOUT_SECONDS)
            except FutureTimeoutError:
                # Post-processing still running — keep extraction empty for trace.
                post_status = "timeout"
            except Exception as exc:
                post_status = "failed"
                post_error = str(exc)
                _logger.debug("Post-processing failed when writing trace: %s", exc)

            trace_id = self.traces.write_trace(
                session_id=session_id,
                input_message_id=user_message_id,
                reply_message_id=assistant_message_id,
                payload={
                    "retrieved_memories": [
                        {
                            "id": str(record.metadata.get("memory_id", record.id)),
                            "tier": str(record.metadata.get("tier", "")),
                            "hms_score": str(record.metadata.get("hms_score", "")),
                            "retrieval_rank": str(record.metadata.get("retrieval_rank", "")),
                        }
                        for record in getattr(bundle, "retrieved_memories", [])
                    ],
                    "retrieved_facts": getattr(bundle, "story_summary", None),
                    "personality_state": self._personality_state(),
                    "mood_snapshot": {
                        "user_mood": mood.user_mood,
                        "companion_state": mood.companion_state,
                        "confidence": mood.confidence,
                        "rationale": mood.rationale,
                    },
                    "prompt_sections": getattr(bundle, "prompt_sections", []),
                    "workspace_skill_files": getattr(bundle, "workspace_skill_files", []),
                    "provider": llm_result.provider,
                    "model": llm_result.model,
                    "response_latency_ms": latency_ms,
                    "assistant_text_length": len(llm_result.text),
                    "extraction_outputs": post_turn,
                    "post_processing_status": post_status,
                    "post_processing_error": post_error,
                    "persisted_records": post_turn.get("persisted_records", {}),
                },
            )
            return ConversationTurnResult(
                session_id=session_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                mood=mood,
                llm_result=llm_result,
                trace_id=trace_id,
                prompt_sections=list(getattr(bundle, "prompt_sections", [])),
                post_process_future=post_future,
            )
        except Exception as exc:
            trace_id = self.traces.write_trace(
                session_id=session_id,
                input_message_id=user_message_id,
                reply_message_id=None,
                status="failed",
                error=str(exc),
                payload={
                    "retrieved_facts": getattr(bundle, "story_summary", None),
                    "personality_state": self._personality_state(),
                    "mood_snapshot": {
                        "user_mood": mood.user_mood,
                        "companion_state": mood.companion_state,
                        "confidence": mood.confidence,
                        "rationale": mood.rationale,
                    },
                    "prompt_sections": getattr(bundle, "prompt_sections", []),
                    "workspace_skill_files": getattr(bundle, "workspace_skill_files", []),
                    "post_processing_status": "not_started",
                    "post_processing_error": None,
                },
            )
            raise TurnExecutionError(f"Turn failed after trace {trace_id}: {exc}") from exc

    def shutdown(self) -> None:
        """Drain background threads (call on session end)."""
        self.post_processor.shutdown()

    def _personality_state(self) -> dict[str, object]:
        builder = getattr(self.context_loader, "builder", None)
        personality_repo = getattr(builder, "personality_repo", None)
        if personality_repo is None:
            return {}
        state = personality_repo.get_current_state()
        return state if isinstance(state, dict) else {}
