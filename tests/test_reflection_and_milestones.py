from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from soul import db
from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.core.post_processor import PostProcessor
from soul.evolution.reflection import ReflectionEntry, ReflectionRepository
import soul.cli as cli
from sqlalchemy import text
from typer.testing import CliRunner


def test_reflection_repository_round_trips_entries(tmp_path):
    path = tmp_path / "nested" / "reflections.json"
    repo = ReflectionRepository(path)

    assert repo.load() == []

    first = ReflectionEntry(date="2026-03-19", summary="First reflection", insights=["slow drift", "care"])
    second = ReflectionEntry(date="2026-03-26", summary="Second reflection", insights=["memory", "continuity"])
    repo.append(first)
    repo.append(second)

    loaded = repo.load()

    assert [entry.summary for entry in loaded] == ["First reflection", "Second reflection"]
    assert loaded[0].insights == ["slow drift", "care"]
    assert path.exists()


def test_post_processor_records_milestones_and_story_updates(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="local-user",
    )
    session_id = db.create_session(database_url, "Ara")
    processor = PostProcessor(settings)
    mood = MoodSnapshot(user_mood="venting", companion_state="warm", confidence=0.9, rationale="heuristic")

    for index in range(99):
        db.log_message(database_url, session_id=session_id, role="user", content=f"Message {index} from the user.")

    db.log_message(
        database_url,
        session_id=session_id,
        role="user",
        content="I launched the beta and I feel invisible, stressed, and alone.",
    )

    processor.process_turn(
        session_id=session_id,
        user_text="I launched the beta and I feel invisible, stressed, and alone.",
        assistant_text="I am here.",
        mood=mood,
    )

    processor.process_turn(
        session_id=session_id,
        user_text="I launched the beta and I feel invisible, stressed, and alone.",
        assistant_text="I am here.",
        mood=mood,
    )

    milestones = db.list_milestones(database_url)
    story = processor.story_repo.load()

    assert db.milestone_exists(database_url, "first_conversation")
    assert db.milestone_exists(database_url, "hundredth_message")
    assert db.milestone_exists(database_url, "first_vulnerable_share")
    assert any(str(item["kind"]).startswith("major_life_event_") for item in milestones)
    assert len(milestones) == 4
    assert story.current_chapter["current_mood_trend"] == "venting"
    assert story.big_moments
    assert story.big_moments[0].companion_was_there is True


def test_post_processor_writes_stressed_turn_to_episodic_memory_immediately(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="local-user",
    )
    session_id = db.create_session(database_url, "Ara")
    processor = PostProcessor(settings)
    mood = MoodSnapshot(user_mood="stressed", companion_state="warm", confidence=0.9, rationale="heuristic")
    user_text = "I am stressed about the product launch and need a breather right now tonight."

    processor.process_turn(
        session_id=session_id,
        user_text=user_text,
        assistant_text="I am here.",
        mood=mood,
    )

    episodic_rows = db.list_episodic_memories(database_url, user_id=settings.user_id, include_cold=True, limit=10)
    sql_rows = db.list_memories(database_url, limit=10)

    assert len(episodic_rows) == 1
    assert str(episodic_rows[0]["emotional_tag"]) == "stressed"
    assert len(sql_rows) == 1
    assert str(sql_rows[0]["label"]) == "stressed moment"
    assert str(sql_rows[0]["content"]) == user_text


def test_post_processor_tracks_recurring_phrase_and_dedupes_major_life_events(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="local-user",
    )
    session_id = db.create_session(database_url, "Ara")
    processor = PostProcessor(settings)
    mood = MoodSnapshot(user_mood="reflective", companion_state="curious", confidence=0.9, rationale="heuristic")

    processor.process_turn(
        session_id=session_id,
        user_text="Late night coding still feels like home.",
        assistant_text="Tell me more.",
        mood=mood,
    )
    processor.process_turn(
        session_id=session_id,
        user_text="Late night coding still feels like home. I launched the beta.",
        assistant_text="That matters.",
        mood=mood,
    )
    processor.process_turn(
        session_id=session_id,
        user_text="Late night coding still feels like home. I launched the beta.",
        assistant_text="That matters.",
        mood=mood,
    )

    story = processor.story_repo.load()
    milestones = db.list_milestones(database_url)

    assert db.milestone_exists(database_url, "first_recurring_phrase")
    assert any(str(item["kind"]).startswith("major_life_event_") for item in milestones)
    assert len(story.big_moments) == 1


def test_post_processor_tracks_streak_and_anniversary_milestones(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="local-user",
    )
    processor = PostProcessor(settings)
    now = datetime.now(timezone.utc)

    anniversary_session = db.create_session(database_url, "Ara")
    streak_sessions = [db.create_session(database_url, "Ara") for _ in range(7)]
    for offset, session_id in enumerate(streak_sessions):
        day = now - timedelta(days=6 - offset)
        db.log_message(database_url, session_id=session_id, role="user", content=f"Day {offset} check-in.")
        with db.connect(database_url) as connection:
            connection.execute(
                text("UPDATE sessions SET started_at = :started_at, ended_at = :ended_at WHERE id = :session_id"),
                {
                    "started_at": day.replace(microsecond=0).isoformat(),
                    "ended_at": day.replace(microsecond=0).isoformat(),
                    "session_id": session_id,
                },
            )
            connection.commit()

    oldest = now - timedelta(days=31)
    with db.connect(database_url) as connection:
        connection.execute(
            text("UPDATE sessions SET started_at = :started_at, ended_at = :ended_at WHERE id = :session_id"),
            {
                "started_at": oldest.replace(microsecond=0).isoformat(),
                "ended_at": oldest.replace(microsecond=0).isoformat(),
                "session_id": anniversary_session,
            },
        )
        connection.commit()

    current_session = db.create_session(database_url, "Ara")
    processor.process_turn(
        session_id=current_session,
        user_text="I had a rough day but I showed up again.",
        assistant_text="I noticed.",
        mood=MoodSnapshot(user_mood="venting", companion_state="warm", confidence=0.8, rationale="heuristic"),
    )

    assert db.milestone_exists(database_url, "seven_day_streak")
    assert db.milestone_exists(database_url, "one_month_anniversary")


def test_story_edit_reports_path_without_opening_an_editor(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    result = CliRunner().invoke(cli.app, ["story", "edit"])

    assert result.exit_code == 0
    assert "Story file:" in result.stdout
    assert settings.user_story_file.name in result.stdout


def test_story_edit_uses_configured_editor(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    commands: list[list[str]] = []

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))
    monkeypatch.setenv("SOUL_EDITOR", "custom-editor --wait")
    monkeypatch.setattr(cli.subprocess, "run", lambda command, check=False: commands.append(command))

    result = CliRunner().invoke(cli.app, ["story", "edit"])

    assert result.exit_code == 0
    assert commands == [["custom-editor", "--wait", str(settings.user_story_file)]]


def test_post_processor_dedupes_near_identical_big_moments_by_normalized_hash(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="local-user",
    )
    session_id = db.create_session(database_url, "Ara")
    processor = PostProcessor(settings)
    mood = MoodSnapshot(user_mood="celebrating", companion_state="warm", confidence=0.9, rationale="heuristic")

    processor.process_turn(
        session_id=session_id,
        user_text="I launched the beta.",
        assistant_text="That matters.",
        mood=mood,
    )
    processor.process_turn(
        session_id=session_id,
        user_text="I   launched   the beta.",
        assistant_text="That matters.",
        mood=mood,
    )

    story = processor.story_repo.load()

    assert len(story.big_moments) == 1


def test_post_processor_does_not_fire_streak_or_anniversary_from_same_day_sessions(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'soul.db').as_posix()}"
    db.init_db(database_url)

    settings = Settings(
        database_url=database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="local-user",
    )
    processor = PostProcessor(settings)
    today = datetime.now(timezone.utc).replace(microsecond=0)

    same_day_sessions = [db.create_session(database_url, "Ara") for _ in range(7)]
    for index, session_id in enumerate(same_day_sessions):
        db.log_message(database_url, session_id=session_id, role="user", content=f"Same day check-in {index}.")
        with db.connect(database_url) as connection:
            connection.execute(
                text("UPDATE sessions SET started_at = :started_at, ended_at = :ended_at WHERE id = :session_id"),
                {
                    "started_at": today.isoformat(),
                    "ended_at": today.isoformat(),
                    "session_id": session_id,
                },
            )
            connection.commit()

    current_session = db.create_session(database_url, "Ara")
    processor.process_turn(
        session_id=current_session,
        user_text="I had a rough day but I showed up again.",
        assistant_text="I noticed.",
        mood=MoodSnapshot(user_mood="venting", companion_state="warm", confidence=0.8, rationale="heuristic"),
    )

    assert not db.milestone_exists(database_url, "seven_day_streak")
    assert not db.milestone_exists(database_url, "one_month_anniversary")
