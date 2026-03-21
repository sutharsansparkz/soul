from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

from soul import db
import soul.cli as cli
from soul.config import Settings
from soul.core.mood_engine import MoodEngine
from soul.core.post_processor import PostProcessor
from soul.tasks.consolidate import StructuredSessionInsights, consolidate_day
from typer.testing import CliRunner


def test_mood_engine_uses_local_state_cache_when_redis_is_unavailable(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
    )
    engine = MoodEngine(settings)
    monkeypatch.setattr(
        MoodEngine,
        "_openai_mood",
        lambda self, text: ("venting", 0.85, "mock"),
    )

    snapshot = engine.analyze("I had a rough day today.")

    assert snapshot.user_mood == "venting"
    assert snapshot.companion_state == "warm"


def test_mood_engine_decays_to_neutral_after_decay_window():
    settings = Settings(
        redis_url="redis://localhost:6399/0",
        mood_decay_hours=18,
    )
    engine = MoodEngine(settings)
    state = engine._select_companion_state(  # noqa: SLF001
        "neutral",
        previous_state={"state": "concerned", "updated_at": "2026-03-18T00:00:00+00:00"},
        now=datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc),
    )
    assert state == "neutral"


def test_consolidate_day_updates_story_and_memory_files(tmp_path):
    session_log = tmp_path / "latest_session.log"
    story_path = tmp_path / "user_story.json"
    memory_path = tmp_path / "episodic_memory.jsonl"
    shared_path = tmp_path / "shared_language.json"
    session_log.write_text(
        "\n".join(
            [
                "user: I had a rough day and felt invisible in the meeting.",
                "assistant: Tell me more.",
                "user: I launched the beta and I am excited but also anxious.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = consolidate_day(session_log, story_path, memory_path, shared_path)

    assert result.processed_messages == 3
    assert result.memories_added >= 1
    assert result.story_updated is True
    assert memory_path.exists()
    assert story_path.exists()

    story = json.loads(story_path.read_text(encoding="utf-8"))
    assert "current_chapter" in story
    assert "summary" in story["current_chapter"]


def test_consolidate_day_merges_structured_insights_when_available(tmp_path, monkeypatch):
    session_log = tmp_path / "latest_session.log"
    story_path = tmp_path / "user_story.json"
    memory_path = tmp_path / "episodic_memory.jsonl"
    shared_path = tmp_path / "shared_language.json"
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    session_log.write_text(
        "\n".join(
            [
                "user: I'm trying to launch this thing without burning out.",
                "assistant: Tell me more.",
                "user: Priya is my best friend and tiny rituals matter to me.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "soul.tasks.consolidate._extract_structured_insights",
        lambda user_lines, settings: StructuredSessionInsights(
            summary="They are trying to launch something meaningful without burning out.",
            current_mood_trend="reflective",
            active_goals=["launch this thing"],
            active_fears=["burning out"],
            values_observed=["consistency"],
            things_they_love=["tiny rituals"],
            relationships=[{"name": "Priya", "role": "best friend", "notes": "trusted confidant"}],
            shared_phrases=["tiny rituals"],
        ),
    )

    result = consolidate_day(session_log, story_path, memory_path, shared_path, settings=settings)

    assert result.story_updated is True
    story = json.loads(story_path.read_text(encoding="utf-8"))
    shared_language = json.loads(shared_path.read_text(encoding="utf-8"))
    assert story["current_chapter"]["summary"] == "They are trying to launch something meaningful without burning out."
    assert "launch this thing" in story["current_chapter"]["active_goals"]
    assert "burning out" in story["current_chapter"]["active_fears"]
    assert story["relationships"][0]["name"] == "Priya"
    assert any(item["phrase"] == "tiny rituals" for item in shared_language)


def test_chat_voice_mode_uses_recording_when_prompt_is_blank(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)

    class FakeContextBuilder:
        def __init__(self, settings, soul):  # noqa: ANN001, ARG002
            pass

        def build(self, *, session_id, user_input, mood):  # noqa: ANN001, ARG002
            return SimpleNamespace(system_prompt="system", messages=[{"role": "user", "content": user_input}])

    class FakeLLMClient:
        def __init__(self, settings, soul):  # noqa: ANN001, ARG002
            pass

        def reply(self, *, system_prompt, messages, mood, stream_handler=None):  # noqa: ANN001, ARG002
            if stream_handler is not None:
                stream_handler("I heard you.")
            return SimpleNamespace(
                text="I heard you.",
                provider="mock-openai",
                model="test-model",
                fallback_used=False,
                error=None,
            )

    class FakeVoiceBridge:
        def __init__(self, settings):  # noqa: ANN001, ARG002
            pass

        def transcribe(self, audio_path):  # noqa: ANN001, ARG002
            return SimpleNamespace(ok=True, text="voice hello", backend="whisper", error=None)

        def record_to_file(self, *, seconds, sample_rate=16000, output_path=None):  # noqa: ANN001, ARG002
            return SimpleNamespace(ok=True, output_path="capture.wav", backend="sounddevice", error=None)

        def speak(self, text):  # noqa: ANN001, ARG002
            return SimpleNamespace(ok=False, output_path=None, backend="elevenlabs", error="disabled")

    prompts = iter(["", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))
    monkeypatch.setattr(cli, "ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr(cli, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(cli, "VoiceBridge", FakeVoiceBridge)
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))

    result = CliRunner().invoke(cli.app, ["chat", "--voice"])

    assert result.exit_code == 0
    session_id = db.get_last_completed_session_id(settings.database_url)
    messages = db.get_session_messages(settings.database_url, session_id)
    assert any(row["role"] == "user" and row["content"] == "voice hello" for row in messages)
    assert any(row["role"] == "assistant" and row["content"] == "I heard you." for row in messages)


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
