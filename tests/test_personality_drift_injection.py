from __future__ import annotations

from soul import db
from soul.config import Settings
from soul.core.context_builder import ContextBuilder
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.memory.repositories.user_facts import UserFactsRepository


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
    PersonalityStateRepository(settings.database_url, user_id=settings.user_id).record_state(
        {
            "humor_intensity": 0.68,
            "response_length": 0.50,
            "curiosity_depth": 0.50,
            "directness": 0.50,
            "warmth_expression": 0.32,
        },
        resonance_signals={},
        notes="seed",
        source="test",
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
    PersonalityStateRepository(settings.database_url, user_id=settings.user_id).record_state(
        {
            "humor_intensity": 0.5,
            "response_length": 0.5,
            "curiosity_depth": 0.5,
            "directness": 0.5,
            "warmth_expression": 0.5,
        },
        resonance_signals={},
        notes="seed",
        source="test",
    )

    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, _soul())
    mood = MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=0.5, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="hello", mood=mood)

    assert "[personality_drift]" not in bundle.system_prompt


def test_personality_context_omitted_when_no_personality_state_exists(tmp_path):
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
    PersonalityStateRepository(settings.database_url, user_id=settings.user_id).record_state(
        {
            "humor_intensity": 0.70,
            "response_length": 0.5,
            "curiosity_depth": 0.5,
            "directness": 0.5,
            "warmth_expression": 0.5,
        },
        resonance_signals={},
        notes="seed",
        source="test",
    )

    story_repo = UserFactsRepository(settings.database_url, user_id=settings.user_id)
    story = story_repo.load_story()
    story.current_chapter["summary"] = "They are carrying a lot."
    story_repo.save_story(story, source="test")

    EpisodicMemoryRepository(settings=settings).add_text(
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
