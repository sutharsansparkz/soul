from __future__ import annotations

import json

from soul import db
from soul.config import Settings
from soul.core.context_builder import ContextBuilder
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.user_story import UserStoryRepository


def _soul() -> Soul:
    return Soul(
        raw={
            "identity": {"name": "Ara", "voice": "warm", "energy": "steady"},
            "character": {},
            "ethics": {},
            "worldview": {},
        },
        name="Ara",
        voice="warm",
        energy="steady",
    )


def test_personality_context_injected_when_drifted(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    settings.personality_file.parent.mkdir(parents=True, exist_ok=True)
    settings.personality_file.write_text(
        json.dumps(
            {
                "humor_intensity": 0.68,
                "response_length": 0.50,
                "curiosity_depth": 0.50,
                "directness": 0.50,
                "warmth_expression": 0.32,
            }
        ),
        encoding="utf-8",
    )

    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, _soul())
    mood = MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=0.5, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="hello", mood=mood)

    assert "[personality_drift]" in bundle.system_prompt
    assert "humor intensity" in bundle.system_prompt
    assert "warmth expression" in bundle.system_prompt
    assert "response length" not in bundle.system_prompt


def test_personality_context_omitted_when_at_baseline(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    settings.personality_file.parent.mkdir(parents=True, exist_ok=True)
    settings.personality_file.write_text(
        json.dumps(
            {
                "humor_intensity": 0.5,
                "response_length": 0.5,
                "curiosity_depth": 0.5,
                "directness": 0.5,
                "warmth_expression": 0.5,
            }
        ),
        encoding="utf-8",
    )

    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, _soul())
    mood = MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=0.5, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="hello", mood=mood)

    assert "[personality_drift]" not in bundle.system_prompt


def test_personality_context_omitted_when_file_missing(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)

    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, _soul())
    mood = MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=0.5, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="hello", mood=mood)

    assert "[personality_drift]" not in bundle.system_prompt


def test_personality_context_appears_after_story_before_memories(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    settings.personality_file.parent.mkdir(parents=True, exist_ok=True)
    settings.personality_file.write_text(
        json.dumps(
            {
                "humor_intensity": 0.70,
                "response_length": 0.5,
                "curiosity_depth": 0.5,
                "directness": 0.5,
                "warmth_expression": 0.5,
            }
        ),
        encoding="utf-8",
    )

    story = UserStoryRepository(settings.user_story_file).load()
    story.current_chapter["summary"] = "They are carrying a lot."
    UserStoryRepository(settings.user_story_file).save(story)

    EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings).add_text(
        "hello there",
        metadata={"user_id": settings.user_id, "timestamp": "2026-03-19T10:00:00+00:00"},
    )

    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, _soul())
    mood = MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=0.5, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="hello", mood=mood)

    prompt = bundle.system_prompt
    soul_pos = prompt.index("You are SOUL")
    story_pos = prompt.index("[user_story]")
    drift_pos = prompt.index("[personality_drift]")
    memory_pos = prompt.index("[memory_context]")
    assert soul_pos < story_pos < drift_pos < memory_pos
