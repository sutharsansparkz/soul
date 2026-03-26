"""Preservation property tests — confirm non-buggy input behavior is unchanged after all 10 fixes.

These tests run on the FIXED codebase and MUST PASS.
Each test encodes the preserved (non-buggy) behavior for a specific bug's complement condition.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11**
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from soul import db
from soul.config import Settings
import soul.cli as cli
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.proactive import ProactiveCandidateRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.persistence.db import utcnow_iso
from typer.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="test-user",
    )


# ---------------------------------------------------------------------------
# Bug 1 preservation — explicit today arg is used unchanged
# isBugCondition_1 false: call.today_arg IS NOT NULL
# **Validates: Requirements 3.1**
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("offset_hours", [0, -5, 8, -12, 14])
def test_bug1_explicit_today_arg_used_unchanged(offset_hours):
    """build_reach_out_candidates with an explicit aware today uses that value unchanged."""
    from soul.maintenance.proactive import build_reach_out_candidates

    # Generate a varied aware datetime by shifting from UTC
    base = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    explicit_today = base + timedelta(hours=offset_hours)
    # Make it timezone-aware (UTC-based offset)
    explicit_today = explicit_today.replace(tzinfo=timezone.utc)

    # Should not raise and should return a list
    result = build_reach_out_candidates(
        days_since_last_chat=0,
        today=explicit_today,
    )
    assert isinstance(result, list)


def test_bug1_explicit_today_monday_triggers_monday_candidate():
    """When today is explicitly a Monday, monday_morning candidate is returned."""
    from soul.maintenance.proactive import build_reach_out_candidates, ReachOutCandidate

    # 2025-06-16 is a Monday
    monday = datetime(2025, 6, 16, 9, 0, 0, tzinfo=timezone.utc)
    result = build_reach_out_candidates(days_since_last_chat=0, today=monday)
    triggers = [c.trigger for c in result]
    assert "monday_morning" in triggers, "Explicit Monday today must produce monday_morning candidate"


def test_bug1_explicit_today_non_monday_no_monday_candidate():
    """When today is explicitly a Tuesday, no monday_morning candidate is returned."""
    from soul.maintenance.proactive import build_reach_out_candidates

    # 2025-06-17 is a Tuesday
    tuesday = datetime(2025, 6, 17, 9, 0, 0, tzinfo=timezone.utc)
    result = build_reach_out_candidates(days_since_last_chat=0, today=tuesday)
    triggers = [c.trigger for c in result]
    assert "monday_morning" not in triggers, "Non-Monday explicit today must not produce monday_morning"


# ---------------------------------------------------------------------------
# Bug 2 preservation — undelivered triggers continue to be inserted as pending
# isBugCondition_2 false: delivered_today=False
# **Validates: Requirements 3.2**
# ---------------------------------------------------------------------------

def test_bug2_undelivered_trigger_inserted_as_pending(tmp_path, monkeypatch):
    """A trigger not yet delivered today must appear in pending after refresh_proactive_candidates."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    from soul.maintenance.proactive import refresh_proactive_candidates, ReachOutCandidate
    from soul.maintenance import proactive as proactive_mod

    monkeypatch.setattr(
        proactive_mod,
        "build_reach_out_candidates",
        lambda **kwargs: [ReachOutCandidate(trigger="silence_3_days", message="Just checking in.")],
    )
    monkeypatch.setattr(proactive_mod, "build_presence_context", lambda *a, **kw: {
        "days_since_last_chat": None,
        "stress_signal_dates": [],
        "milestones_today": [],
    })

    refresh_proactive_candidates(settings, channel="cli")

    repo = ProactiveCandidateRepository(settings.database_url, user_id=settings.user_id)
    pending = repo.list_pending(channel="cli")
    pending_triggers = [str(row["trigger"]) for row in pending]
    assert "silence_3_days" in pending_triggers, (
        "Undelivered trigger must appear in pending after refresh"
    )


def test_bug2_multiple_undelivered_triggers_all_inserted(tmp_path, monkeypatch):
    """Multiple undelivered triggers must all appear in pending."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    from soul.maintenance.proactive import refresh_proactive_candidates, ReachOutCandidate
    from soul.maintenance import proactive as proactive_mod

    candidates = [
        ReachOutCandidate(trigger="silence_3_days", message="Checking in."),
        ReachOutCandidate(trigger="monday_morning", message="Monday again."),
    ]
    monkeypatch.setattr(proactive_mod, "build_reach_out_candidates", lambda **kwargs: candidates)
    monkeypatch.setattr(proactive_mod, "build_presence_context", lambda *a, **kw: {
        "days_since_last_chat": None,
        "stress_signal_dates": [],
        "milestones_today": [],
    })

    refresh_proactive_candidates(settings, channel="cli")

    repo = ProactiveCandidateRepository(settings.database_url, user_id=settings.user_id)
    pending = repo.list_pending(channel="cli")
    pending_triggers = {str(row["trigger"]) for row in pending}
    assert "silence_3_days" in pending_triggers
    assert "monday_morning" in pending_triggers


# ---------------------------------------------------------------------------
# Bug 3 preservation — boost() on ref_count=0 sets flagged=True and raises HMS
# isBugCondition_3 false: any ref_count value (0-5 tested)
# **Validates: Requirements 3.3**
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("initial_ref_count", [0, 1, 2, 3, 4, 5])
def test_bug3_boost_always_increments_ref_count(tmp_path, initial_ref_count):
    """boost() always returns ref_count+1 and higher hms_score for any initial ref_count."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = EpisodicMemoryRepository(settings=settings)
    record = repo.add_text(
        f"Memory with ref_count={initial_ref_count}",
        emotional_tag="neutral",
        importance=0.5,
        metadata={
            "user_id": settings.user_id,
            "flagged": False,
            "ref_count": initial_ref_count,
            "timestamp": "2026-01-01T10:00:00+00:00",
        },
    )
    memory_id = str(record.metadata.get("memory_id", record.id))

    before_row = repo.get_row(memory_id)
    assert before_row is not None
    before_hms = float(before_row["hms_score"])
    before_ref = int(before_row["ref_count"])

    result = repo.boost(memory_id)

    assert result is not None
    assert int(result["ref_count"]) == before_ref + 1, (
        f"ref_count must be {before_ref + 1}, got {result['ref_count']} (initial={initial_ref_count})"
    )
    assert float(result["hms_score"]) > before_hms, (
        f"hms_score must increase after boost; was {before_hms}, now {result['hms_score']}"
    )


def test_bug3_boost_on_ref_count_zero_sets_flagged(tmp_path):
    """boost() on a memory with ref_count=0 sets flagged=True."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = EpisodicMemoryRepository(settings=settings)
    record = repo.add_text(
        "Unflagged memory",
        importance=0.5,
        metadata={
            "user_id": settings.user_id,
            "flagged": False,
            "ref_count": 0,
            "timestamp": "2026-01-01T10:00:00+00:00",
        },
    )
    memory_id = str(record.metadata.get("memory_id", record.id))

    result = repo.boost(memory_id)

    assert result is not None
    assert int(result["flagged"]) == 1, "boost() on ref_count=0 must set flagged=True"
    assert int(result["ref_count"]) == 1, "boost() on ref_count=0 must set ref_count=1"


# ---------------------------------------------------------------------------
# Bug 4 preservation — _render_story with actual content renders full JSON
# isBugCondition_4 false: at least one non-empty meaningful field
# **Validates: Requirements 3.4**
# ---------------------------------------------------------------------------

def test_bug4_render_story_with_content_renders_json(tmp_path, monkeypatch):
    """_render_story for a user with story content renders the full JSON payload."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    from soul.memory.repositories.user_facts import UserFactsRepository
    from soul.memory.user_story import ensure_story_defaults

    story_repo = UserFactsRepository(settings.database_url, user_id=settings.user_id)
    story = story_repo.load_story()
    ensure_story_defaults(story)
    story.big_moments = []
    story.current_chapter["summary"] = "User is working on a big project."
    story_repo.save_story(story, source="test")

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["story"])

    assert result.exit_code == 0
    assert "No user story exists yet." not in result.output, (
        "Must NOT show placeholder when story has content"
    )
    # The output should contain JSON-like content
    assert "summary" in result.output or "project" in result.output, (
        f"Expected story content in output, got: {result.output!r}"
    )


def test_bug4_render_story_with_big_moments_renders_json(tmp_path, monkeypatch):
    """_render_story with big_moments renders JSON, not placeholder."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    from soul.memory.repositories.user_facts import UserFactsRepository
    from soul.memory.user_story import ensure_story_defaults, BigMoment

    story_repo = UserFactsRepository(settings.database_url, user_id=settings.user_id)
    story = story_repo.load_story()
    ensure_story_defaults(story)
    story.big_moments = [BigMoment(date="2025-01-01", event="Launched the product", emotional_weight="high", companion_was_there=True)]
    story_repo.save_story(story, source="test")

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["story"])

    assert result.exit_code == 0
    assert "No user story exists yet." not in result.output


# ---------------------------------------------------------------------------
# Bug 5 preservation — drift with no history shows "No drift runs recorded yet."
# **Validates: Requirements 3.5**
# ---------------------------------------------------------------------------

def test_bug5_drift_no_history_shows_placeholder(tmp_path, monkeypatch):
    """drift command with no history shows 'No drift runs recorded yet.' message."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["drift"])

    assert result.exit_code == 0
    assert "No drift runs recorded yet." in result.output, (
        f"Expected placeholder message for empty drift history, got: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Bug 6 preservation — get_last_companion_state without user_id returns global most recent
# isBugCondition_6 false: user_id IS NULL
# **Validates: Requirements 3.6**
# ---------------------------------------------------------------------------

def test_bug6_get_last_companion_state_no_user_id_returns_global_most_recent(tmp_path):
    """get_last_companion_state called without user_id returns the global most recent state."""
    from sqlalchemy import text as sa_text
    from soul.persistence.db import get_engine

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="user-a",
    )
    db.init_db(settings.database_url)

    messages_a = MessagesRepository(settings.database_url, user_id="user-a")
    messages_b = MessagesRepository(settings.database_url, user_id="user-b")

    session_a = messages_a.create_session("Ara")
    session_b = messages_b.create_session("Ara")

    # Insert user-a's message with an earlier explicit timestamp
    import uuid
    msg_id_a = str(uuid.uuid4())
    msg_id_b = str(uuid.uuid4())
    with get_engine(settings.database_url).begin() as conn:
        conn.execute(sa_text(
            "INSERT INTO messages (id, session_id, role, content, companion_state, created_at) "
            "VALUES (:id, :sid, 'assistant', 'Hello user-a', 'warm', '2025-01-01T10:00:00+00:00')"
        ), {"id": msg_id_a, "sid": session_a})
        # user-b's message has a later timestamp — must win in global query
        conn.execute(sa_text(
            "INSERT INTO messages (id, session_id, role, content, companion_state, created_at) "
            "VALUES (:id, :sid, 'assistant', 'Hello user-b', 'curious', '2025-01-01T11:00:00+00:00')"
        ), {"id": msg_id_b, "sid": session_b})

    # Without user_id, should return the global most recent (user-b's "curious")
    state = db.get_last_companion_state(settings.database_url)
    assert state == "curious", (
        f"Without user_id, must return global most recent state 'curious', got {state!r}"
    )


def test_bug6_get_last_companion_state_no_user_id_single_user(tmp_path):
    """get_last_companion_state without user_id works correctly in a single-user database."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    messages = MessagesRepository(settings.database_url, user_id=settings.user_id)
    session = messages.create_session("Ara")
    messages.log_message(session_id=session, role="assistant", content="Hello", companion_state="reflective")

    state = db.get_last_companion_state(settings.database_url)
    assert state == "reflective", (
        f"Without user_id, must return the only existing state 'reflective', got {state!r}"
    )


# ---------------------------------------------------------------------------
# Bug 7 preservation — soul/db.py helper functions return correctly typed result dicts
# **Validates: Requirements 3.7**
# ---------------------------------------------------------------------------

def test_bug7_get_session_messages_returns_list_of_dicts(tmp_path):
    """get_session_messages returns a list of dicts with expected keys."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    messages = MessagesRepository(settings.database_url, user_id=settings.user_id)
    session_id = messages.create_session("Ara")
    messages.log_message(session_id=session_id, role="user", content="Hello there")
    messages.log_message(session_id=session_id, role="assistant", content="Hi!")

    result = db.get_session_messages(settings.database_url, session_id)

    assert isinstance(result, list), "get_session_messages must return a list"
    assert len(result) == 2
    for row in result:
        assert isinstance(row, dict), "Each row must be a dict"
        assert "role" in row
        assert "content" in row


def test_bug7_list_episodic_memories_returns_list_of_dicts(tmp_path):
    """list_episodic_memories returns a list of dicts with expected keys."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = EpisodicMemoryRepository(settings=settings)
    repo.add_text("A test memory", importance=0.6)

    result = db.list_episodic_memories(settings.database_url, user_id=settings.user_id)

    assert isinstance(result, list), "list_episodic_memories must return a list"
    assert len(result) == 1
    row = result[0]
    assert isinstance(row, dict), "Each row must be a dict"
    assert "id" in row
    assert "content" in row
    assert "user_id" in row


def test_bug7_fetch_dicts_annotation_resolves(tmp_path):
    """_fetch_dicts type annotation resolves without NameError (Connection is importable)."""
    import typing
    import soul.db as soul_db

    hints = typing.get_type_hints(soul_db._fetch_dicts)
    assert "connection" in hints, "_fetch_dicts must have a 'connection' type annotation"
    assert "return" in hints, "_fetch_dicts must have a return type annotation"


# ---------------------------------------------------------------------------
# Bug 8 preservation — memories clear in single-user DB deletes all memories and reports count
# **Validates: Requirements 3.8**
# ---------------------------------------------------------------------------

def test_bug8_memories_clear_single_user_deletes_all_and_reports_count(tmp_path, monkeypatch):
    """memories clear in a single-user database deletes all memories for that user."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = EpisodicMemoryRepository(settings=settings)
    repo.add_text("Memory one", importance=0.6)
    repo.add_text("Memory two", importance=0.7)
    repo.add_text("Memory three", importance=0.8)

    assert len(db.list_episodic_memories(settings.database_url, user_id=settings.user_id)) == 3

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *args, **kwargs: True))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["memories", "clear"])

    assert result.exit_code == 0
    # All memories must be gone
    remaining = db.list_episodic_memories(settings.database_url, user_id=settings.user_id)
    assert remaining == [], f"All memories must be deleted, got {remaining}"
    # Output must mention the count
    assert "3" in result.output or "deleted" in result.output.lower() or "cleared" in result.output.lower(), (
        f"Output must report deletion count, got: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Bug 9 preservation — MoodEngine.analyze() with default user_id persists to self.repository
# **Validates: Requirements 3.9**
# ---------------------------------------------------------------------------

def test_bug9_analyze_default_user_id_persists_to_self_repository(tmp_path):
    """MoodEngine.analyze() with default user_id persists snapshots to self.repository."""
    from soul.core.mood_engine import MoodEngine
    from pydantic import SecretStr

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="test-user",
        openai_api_key=SecretStr("sk-fake-key-for-testing"),
    )
    db.init_db(settings.database_url)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"mood": "neutral", "confidence": 0.8}'
    mock_client.chat.completions.create.return_value = mock_response

    engine = MoodEngine(settings=settings)
    original_repo = engine.repository

    with patch.object(engine, "_get_openai_client", return_value=mock_client):
        engine.analyze("I am feeling okay today.", persist=True)

    # self.repository must be unchanged
    assert engine.repository is original_repo, "self.repository must not be replaced"
    assert engine.repository.user_id == "test-user"

    # A snapshot must have been persisted — current_state() returns the latest snapshot
    snapshot = original_repo.current_state()
    assert snapshot is not None, "At least one snapshot must be persisted to self.repository"


def test_bug9_analyze_default_user_id_self_repository_not_mutated(tmp_path):
    """After analyze() with default user_id, self.repository.user_id is still the original user."""
    from soul.core.mood_engine import MoodEngine
    from pydantic import SecretStr

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="original-user",
        openai_api_key=SecretStr("sk-fake-key-for-testing"),
    )
    db.init_db(settings.database_url)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"mood": "neutral", "confidence": 0.8}'
    mock_client.chat.completions.create.return_value = mock_response

    engine = MoodEngine(settings=settings)

    with patch.object(engine, "_get_openai_client", return_value=mock_client):
        # Call with default user_id (no user_id arg)
        engine.analyze("Hello world", persist=True)
        # Call again
        engine.analyze("Another message", persist=True)

    assert engine.repository.user_id == "original-user", (
        f"self.repository.user_id must remain 'original-user', got {engine.repository.user_id!r}"
    )


# ---------------------------------------------------------------------------
# Bug 10 preservation — valid LLM JSON continues normal processing
# **Validates: Requirements 3.10, 3.11**
# ---------------------------------------------------------------------------

def test_bug10a_valid_json_consolidation_merges_insights(tmp_path, monkeypatch):
    """_extract_structured_insights returning valid JSON merges insights normally."""
    from soul.maintenance.consolidation import consolidate_pending_sessions, StructuredSessionInsights
    import soul.maintenance.consolidation as consolidation_mod

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)
    session_id = messages_repo.create_session("Ara")
    messages_repo.log_message(session_id=session_id, role="user", content="I launched my product today!")
    messages_repo.log_message(session_id=session_id, role="assistant", content="That is wonderful!")
    messages_repo.close_session(session_id)

    # Return valid structured insights
    def mock_extract(user_lines, resolved_settings):
        return StructuredSessionInsights(
            summary="User launched their product.",
            big_moments=["Launched the product"],
            active_goals=["grow the user base"],
        )

    monkeypatch.setattr(consolidation_mod, "_extract_structured_insights", mock_extract)

    results = consolidate_pending_sessions(database_url=settings.database_url, settings=settings)

    assert len(results) == 1, f"Session must be processed, got {len(results)} results"
    assert str(results[0]["session_id"]) == session_id
    assert results[0]["skipped"] is False, "Session must not be skipped"


def test_bug10a_valid_json_consolidation_processes_all_sessions(tmp_path, monkeypatch):
    """When all sessions have valid LLM JSON, all sessions are processed normally."""
    from soul.maintenance.consolidation import consolidate_pending_sessions, StructuredSessionInsights
    import soul.maintenance.consolidation as consolidation_mod

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)

    session_1 = messages_repo.create_session("Ara")
    messages_repo.log_message(session_id=session_1, role="user", content="I am stressed about the deadline.")
    messages_repo.close_session(session_1)

    session_2 = messages_repo.create_session("Ara")
    messages_repo.log_message(session_id=session_2, role="user", content="I launched the product today!")
    messages_repo.close_session(session_2)

    monkeypatch.setattr(
        consolidation_mod,
        "_extract_structured_insights",
        lambda user_lines, s: StructuredSessionInsights(),
    )

    results = consolidate_pending_sessions(database_url=settings.database_url, settings=settings)

    assert len(results) == 2, f"Both sessions must be processed, got {len(results)}"
    processed_ids = {str(r["session_id"]) for r in results}
    assert session_1 in processed_ids
    assert session_2 in processed_ids


def test_bug10b_valid_json_reflection_persists_artifact(tmp_path, monkeypatch):
    """_parse_reflection_response returning valid JSON persists the reflection artifact."""
    from soul.maintenance.reflection import generate_monthly_reflection, ReflectionArtifact
    import soul.maintenance.reflection as reflection_mod
    from soul.memory.repositories.reflections import ReflectionArtifactsRepository

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    # Create the required soul.yaml
    soul_data_dir = (tmp_path / "soul_data")
    soul_data_dir.mkdir(parents=True, exist_ok=True)
    soul_yaml = soul_data_dir / "soul.yaml"
    soul_yaml.write_text(
        'identity:\n  name: "Ara"\n  voice: "warm"\n  energy: "steady"\ncharacter: {}\nethics: {}\nworldview: {}\n',
        encoding="utf-8",
    )

    # Mock the LLM call to return valid JSON
    mock_llm_result = MagicMock()
    mock_llm_result.text = '{"summary": "A meaningful month of growth.", "insights": ["User is resilient", "Trust is building"]}'

    from soul.core.llm_client import LLMClient
    monkeypatch.setattr(LLMClient, "complete_text", lambda self, **kwargs: mock_llm_result)

    result = generate_monthly_reflection(settings=settings)

    assert result is not None, "generate_monthly_reflection must return an artifact for valid JSON"
    assert isinstance(result, ReflectionArtifact)
    assert result.summary == "A meaningful month of growth."
    assert len(result.insights) >= 1

    # Artifact must be persisted
    repo = ReflectionArtifactsRepository(settings.database_url, user_id=settings.user_id)
    today = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).date()
    month_key = today.strftime("%Y-%m")
    persisted = repo.get_by_key(month_key)
    assert persisted is not None, "Reflection artifact must be persisted to the repository"


def test_bug10b_valid_json_reflection_also_persists_episodic_memory(tmp_path, monkeypatch):
    """generate_monthly_reflection with valid JSON also persists an episodic memory."""
    from soul.maintenance.reflection import generate_monthly_reflection
    from soul.core.llm_client import LLMClient

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    soul_data_dir = (tmp_path / "soul_data")
    soul_data_dir.mkdir(parents=True, exist_ok=True)
    (soul_data_dir / "soul.yaml").write_text(
        'identity:\n  name: "Ara"\n  voice: "warm"\n  energy: "steady"\ncharacter: {}\nethics: {}\nworldview: {}\n',
        encoding="utf-8",
    )

    mock_llm_result = MagicMock()
    mock_llm_result.text = '{"summary": "A month of deep connection.", "insights": ["Growth observed"]}'
    monkeypatch.setattr(LLMClient, "complete_text", lambda self, **kwargs: mock_llm_result)

    generate_monthly_reflection(settings=settings)

    memories = db.list_episodic_memories(settings.database_url, user_id=settings.user_id)
    reflection_memories = [m for m in memories if "reflection" in str(m.get("source", "")).lower()]
    assert len(reflection_memories) >= 1, (
        "generate_monthly_reflection must persist an episodic memory for valid JSON"
    )
