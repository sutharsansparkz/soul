from __future__ import annotations

from datetime import datetime, timedelta, timezone

from soul import db
from soul.config import Settings
from soul.core.context_builder import ContextBuilder
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul
from soul.memory.episodic import EpisodicMemoryRepository


def test_context_builder_orders_mood_tags_before_soul_prompt(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    soul = Soul(
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
    session_id = db.create_session(settings.database_url, "Ara")
    builder = ContextBuilder(settings, soul)
    mood = MoodSnapshot(user_mood="venting", companion_state="warm", confidence=0.9, rationale="test")

    bundle = builder.build(session_id=session_id, user_input="I had a rough day.", mood=mood)

    assert bundle.system_prompt.index("[user_mood: venting]") < bundle.system_prompt.index("You are SOUL")
    assert bundle.system_prompt.index("[companion_state: warm]") < bundle.system_prompt.index("You are SOUL")


def test_context_builder_retrieves_up_to_8_and_injects_top_3_to_5(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    soul = Soul(
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
    session_id = db.create_session(settings.database_url, "Ara")
    db.log_message(settings.database_url, session_id=session_id, role="user", content="Checking in.")
    db.log_message(settings.database_url, session_id=session_id, role="assistant", content="I am listening.")

    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    now = datetime(2026, 3, 19, tzinfo=timezone.utc)
    for index in range(10):
        ts = (now - timedelta(days=index)).isoformat()
        episodic_repo.add_text(
            f"launch memory {index}",
            importance=0.6,
            memory_type="moment",
            metadata={"timestamp": ts},
        )
    db.save_memory(settings.database_url, label="manual launch", content="launch preparation with Priya", importance=0.9)

    builder = ContextBuilder(settings, soul)
    mood = MoodSnapshot(user_mood="curious", companion_state="curious", confidence=0.8, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="launch", mood=mood)

    assert 3 <= len(bundle.memory_snippets) <= 5
    assert all(snippet.startswith("[memory:") for snippet in bundle.memory_snippets)


def test_context_builder_prefers_more_recent_memory_on_ties(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    db.init_db(settings.database_url)
    soul = Soul(
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
    session_id = db.create_session(settings.database_url, "Ara")
    episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
    episodic_repo.add_text(
        "launch planning with investors",
        importance=0.6,
        memory_type="moment",
        metadata={"timestamp": "2026-02-01T10:00:00+00:00"},
    )
    episodic_repo.add_text(
        "launch planning with investors",
        importance=0.6,
        memory_type="moment",
        metadata={"timestamp": "2026-03-18T10:00:00+00:00"},
    )

    builder = ContextBuilder(settings, soul)
    mood = MoodSnapshot(user_mood="curious", companion_state="curious", confidence=0.8, rationale="test")
    bundle = builder.build(session_id=session_id, user_input="launch planning", mood=mood)

    assert bundle.memory_snippets
    assert "launch planning with investors" in bundle.memory_snippets[0]
