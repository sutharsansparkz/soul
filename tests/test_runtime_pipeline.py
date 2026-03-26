from __future__ import annotations

import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from types import SimpleNamespace

from typer.testing import CliRunner

from soul import db
from soul.bootstrap import TurnExecutionError
from soul.conversation.orchestrator import ConversationOrchestrator
from soul.config import Settings
from soul.core.context_builder import ContextBundle
from soul.core.llm_client import LLMResult
from soul.core.mood_engine import MoodSnapshot
from soul.core.post_processor import PostProcessor
from soul.core.soul_loader import Soul
from soul.observability.traces import TurnTraceRepository
import soul.cli as cli


def _soul() -> Soul:
    return Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )


def test_chat_voice_mode_uses_recording_when_prompt_is_blank(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        _env_file=None,
        enable_voice=True,
    )
    db.init_db(settings.database_url)

    class FakeVoiceBridge:
        def __init__(self, settings):  # noqa: ANN001, ARG002
            pass

        def transcribe(self, audio_path):  # noqa: ANN001, ARG002
            return SimpleNamespace(ok=True, text="voice hello", backend="whisper", error=None)

        def record_to_file(self, *, seconds, sample_rate=16000, output_path=None):  # noqa: ANN001, ARG002
            return SimpleNamespace(ok=True, output_path="capture.wav", backend="sounddevice", error=None)

        def speak(self, text, *, output_path=None, autoplay=False):  # noqa: ANN001, ARG002
            return SimpleNamespace(ok=False, output_path=None, backend="elevenlabs", error="disabled")

    prompts = iter(["", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(cli, "VoiceBridge", FakeVoiceBridge)
    monkeypatch.setattr(
        cli.MoodEngine,
        "_openai_mood",
        lambda self, text: ("reflective", 0.85, "mock"),
    )
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))

    def fake_reply(self, *, system_prompt, messages, mood, stream_handler=None):  # noqa: ARG001
        if stream_handler is not None:
            stream_handler("I heard you.")
        return SimpleNamespace(
            text="I heard you.",
            provider="mock-openai",
            model="test-model",
            fallback_used=False,
            error=None,
        )

    monkeypatch.setattr(cli.LLMClient, "reply", fake_reply)

    result = CliRunner().invoke(cli.app, ["chat", "--voice"])

    assert result.exit_code == 0
    session_id = db.get_last_completed_session_id(settings.database_url)
    messages = db.get_session_messages(settings.database_url, session_id)
    assert any(row["role"] == "user" and row["content"] == "voice hello" for row in messages)
    assert any(row["role"] == "assistant" and row["content"] == "I heard you." for row in messages)


def test_chat_shows_turn_trace_and_streams_without_duplicate_reply(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        _env_file=None,
    )
    db.init_db(settings.database_url)

    prompts = iter(["show me the trace", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(
        cli.MoodEngine,
        "_openai_mood",
        lambda self, text: ("reflective", 0.85, "mock"),
    )
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))

    def fake_reply(self, *, system_prompt, messages, mood, stream_handler=None):  # noqa: ARG001
        if stream_handler is not None:
            stream_handler("Hello")
            stream_handler(" world")
        return SimpleNamespace(
            text="Hello world",
            provider="mock-openai",
            model="test-model",
            fallback_used=False,
            error=None,
        )

    monkeypatch.setattr(cli.LLMClient, "reply", fake_reply)

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "inside Ara" in result.stdout
    assert result.stdout.count("Hello world") == 1


def test_chat_answers_clock_query_locally_without_llm_or_memory_export(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        timezone_name="UTC",
    )
    db.init_db(settings.database_url)
    fixed_now = datetime(2026, 3, 23, 15, 45, tzinfo=timezone.utc)
    prompts = iter(["what is the time now", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(cli, "runtime_now", lambda settings, now=None: fixed_now)  # noqa: ARG005
    monkeypatch.setattr(
        cli.MoodEngine,
        "_openai_mood",
        lambda self, text: (_ for _ in ()).throw(AssertionError("clock queries should not call mood classification")),
    )
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "local: clock" in result.stdout
    assert "checking the local clock" in result.stdout
    assert "It's 3:45 PM on Monday, March 23, 2026 (UTC)." in result.stdout

    session_id = db.get_last_completed_session_id(settings.database_url)
    messages = db.get_session_messages(settings.database_url, session_id)
    assert any(row["role"] == "assistant" and row["provider"] == "local-runtime" for row in messages)
    assert db.list_episodic_memories(settings.database_url, user_id=settings.user_id, include_cold=True, limit=20) == []
    assert db.list_memories(settings.database_url, limit=20) == []


def test_process_session_end_exports_only_new_user_rows(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    processor = PostProcessor(settings)
    session_id = db.create_session(settings.database_url, "Ara")

    db.log_message(settings.database_url, session_id=session_id, role="user", content="First thing I wanted to say.")
    db.log_message(settings.database_url, session_id=session_id, role="assistant", content="I am listening.")
    processor.process_session_end(session_id=session_id)

    first_export = db.list_episodic_memories(
        settings.database_url,
        user_id=settings.user_id,
        include_cold=True,
        limit=20,
    )
    assert len(first_export) == 1

    db.log_message(settings.database_url, session_id=session_id, role="user", content="Second thing I needed to add.")
    db.log_message(settings.database_url, session_id=session_id, role="assistant", content="Keep going.")
    processor.process_session_end(session_id=session_id)

    second_export = db.list_episodic_memories(
        settings.database_url,
        user_id=settings.user_id,
        include_cold=True,
        limit=20,
    )
    export_state = db.get_session_memory_export_state(settings.database_url, session_id)

    assert len(second_export) == 2
    assert export_state is not None
    assert int(export_state["exported_user_count"]) == 2

    processor.process_session_end(session_id=session_id)

    third_export = db.list_episodic_memories(
        settings.database_url,
        user_id=settings.user_id,
        include_cold=True,
        limit=20,
    )

    assert len(third_export) == 2


def test_run_turn_captures_post_processing_outputs_when_future_completes_quickly(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        openai_api_key=None,
        _env_file=None,
    )
    db.init_db(settings.database_url)
    session_id = db.create_session(settings.database_url, "Ara")
    orchestrator = ConversationOrchestrator(settings, _soul())

    mood = MoodSnapshot(
        user_mood="reflective",
        companion_state="reflective",
        confidence=0.9,
        rationale="test mood",
    )

    class DelayedFuture:
        def result(self, timeout=None):  # noqa: ANN001
            if timeout is not None and timeout < 0.1:
                raise FutureTimeoutError()
            time.sleep(0.1)
            return {
                "milestones": [{"id": "m-1", "kind": "first_conversation"}],
                "persisted_records": {"auto_memory_id": "memory-1"},
            }

    monkeypatch.setattr(orchestrator.mood_engine, "analyze", lambda *args, **kwargs: mood)
    monkeypatch.setattr(
        orchestrator.context_loader,
        "load",
        lambda *args, **kwargs: ContextBundle(
            system_prompt="system",
            messages=[],
            story_summary=None,
            memory_snippets=[],
            retrieved_memories=[],
            prompt_sections=["mood", "soul_prompt"],
        ),
    )
    monkeypatch.setattr(
        orchestrator.client,
        "reply",
        lambda **kwargs: LLMResult(
            text="I heard you.",
            provider="mock-openai",
            model="test-model",
            fallback_used=False,
        ),
    )
    monkeypatch.setattr(
        orchestrator.post_processor,
        "process_turn_background",
        lambda **kwargs: DelayedFuture(),
    )

    result = orchestrator.run_turn(session_id=session_id, user_text="Capture the trace payload.")
    trace = TurnTraceRepository(settings.database_url, user_id=settings.user_id).get_trace(result.trace_id)
    orchestrator.shutdown()

    assert trace is not None
    assert trace["trace"]["post_processing_status"] == "complete"
    assert trace["trace"]["extraction_outputs"]["persisted_records"] == {"auto_memory_id": "memory-1"}
    assert trace["trace"]["persisted_records"] == {"auto_memory_id": "memory-1"}


def test_chat_reports_turn_failure_and_keeps_session_alive(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        _env_file=None,
    )
    db.init_db(settings.database_url)

    prompts = iter(["hello there", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, _soul()))
    monkeypatch.setattr(
        cli,
        "_run_orchestrated_turn",
        lambda *args, **kwargs: (_ for _ in ()).throw(TurnExecutionError("Turn failed after trace trace-1: Connection error.")),
    )
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))
    monkeypatch.setattr(cli, "trigger_maintenance_if_due", lambda settings: None)  # noqa: ARG005

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "Turn failed." in result.stdout
    assert "trace-1: Connection error." in result.stdout
    session_id = db.get_last_completed_session_id(settings.database_url)
    assert session_id is not None
