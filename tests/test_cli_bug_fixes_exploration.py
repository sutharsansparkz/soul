"""Bug condition exploration tests — confirm all 10 CLI bugs are fixed.

These tests run on the FIXED codebase and MUST PASS.
Each test encodes the expected (correct) behavior for a specific bug condition.
"""
from __future__ import annotations

import typing
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from soul import db
from soul.config import Settings
import soul.cli as cli
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.proactive import ProactiveCandidateRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.persistence.db import utcnow_iso
from typer.testing import CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(tmp_path) -> Settings:  # noqa: ANN001
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="test-user",
    )


# ---------------------------------------------------------------------------
# Bug 1 — Naive datetime in build_reach_out_candidates
# isBugCondition_1: call.today_arg IS NULL
# ---------------------------------------------------------------------------

def test_bug1_build_reach_out_candidates_no_today_arg_no_type_error(tmp_path):
    """Calling build_reach_out_candidates() without today= must not raise TypeError."""
    from soul.maintenance.proactive import build_reach_out_candidates

    # Should not raise TypeError (was: datetime.now() vs aware timestamps)
    result = build_reach_out_candidates(days_since_last_chat=10)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Bug 2a — Delivered-today trigger must not be re-queued as pending
# isBugCondition_2: trigger_delivered_today = TRUE
# ---------------------------------------------------------------------------

def test_bug2a_refresh_proactive_candidates_skips_delivered_today(tmp_path, monkeypatch):
    """A trigger already delivered today must not appear in pending rows after refresh."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = ProactiveCandidateRepository(settings.database_url, user_id=settings.user_id)
    today_iso = utcnow_iso()

    # Pre-insert a delivered row for the "monday_morning" trigger
    repo.replace_pending(
        [
            {
                "trigger": "monday_morning",
                "message": "Monday again.",
                "status": "delivered",
                "channel": "cli",
                "delivered_at": today_iso,
            }
        ],
        channel="cli",
    )
    # Manually update status to delivered (replace_pending inserts as given status)
    from soul.persistence.db import get_engine
    from sqlalchemy import text
    with get_engine(settings.database_url).begin() as conn:
        conn.execute(
            text("UPDATE proactive_candidates SET status='delivered', delivered_at=:da WHERE trigger='monday_morning'"),
            {"da": today_iso},
        )

    from soul.maintenance.proactive import refresh_proactive_candidates

    # Patch build_reach_out_candidates to always return monday_morning candidate
    from soul.maintenance import proactive as proactive_mod
    from soul.maintenance.proactive import ReachOutCandidate

    monkeypatch.setattr(
        proactive_mod,
        "build_reach_out_candidates",
        lambda **kwargs: [ReachOutCandidate(trigger="monday_morning", message="Monday again.")],
    )
    monkeypatch.setattr(proactive_mod, "build_presence_context", lambda *a, **kw: {
        "days_since_last_chat": None,
        "stress_signal_dates": [],
        "milestones_today": [],
    })

    refresh_proactive_candidates(settings, channel="cli")

    pending = repo.list_pending(channel="cli")
    pending_triggers = [str(row["trigger"]) for row in pending]
    assert "monday_morning" not in pending_triggers, (
        "monday_morning was already delivered today — must not be re-queued as pending"
    )


# ---------------------------------------------------------------------------
# Bug 2b — _show_pending_reach_outs must call mark_delivered, not clear_pending
# isBugCondition_2b: clear_pending called instead of mark_delivered
# ---------------------------------------------------------------------------

def test_bug2b_show_pending_reach_outs_marks_delivered_not_deleted(tmp_path, monkeypatch):
    """After _show_pending_reach_outs, rows must have status='delivered', not be deleted."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = ProactiveCandidateRepository(settings.database_url, user_id=settings.user_id)
    repo.replace_pending(
        [{"trigger": "silence_3_days", "message": "Just checking in.", "status": "pending", "channel": "cli"}],
        channel="cli",
    )

    soul_obj = SimpleNamespace(name="Ara")
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, soul_obj))

    # Suppress console output
    monkeypatch.setattr(cli.console, "print", lambda *a, **kw: None)

    cli._show_pending_reach_outs(settings, soul_obj)

    # Row must still exist but with status='delivered'
    all_rows = repo.list(channel="cli", limit=10)
    assert len(all_rows) == 1, "Row must not be deleted — it should be marked delivered"
    assert str(all_rows[0]["status"]) == "delivered", (
        f"Expected status='delivered', got {all_rows[0]['status']!r}"
    )


# ---------------------------------------------------------------------------
# Bug 3 — boost() must increment ref_count even when flagged=True
# isBugCondition_3: memory.flagged=TRUE AND boost called
# ---------------------------------------------------------------------------

def test_bug3_boost_increments_ref_count_when_already_flagged(tmp_path):
    """boost() on a flagged memory must increment ref_count and raise hms_score."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    repo = EpisodicMemoryRepository(settings=settings)
    record = repo.add_text(
        "I launched the beta.",
        emotional_tag="celebrating",
        importance=0.7,
        metadata={
            "user_id": settings.user_id,
            "flagged": True,
            "ref_count": 2,
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
        f"ref_count must be {before_ref + 1}, got {result['ref_count']}"
    )
    assert float(result["hms_score"]) > before_hms, (
        f"hms_score must increase after boost; was {before_hms}, now {result['hms_score']}"
    )


# ---------------------------------------------------------------------------
# Bug 4 — _render_story must show placeholder when all meaningful fields empty
# isBugCondition_4: all meaningful story fields are empty
# ---------------------------------------------------------------------------

def test_bug4_render_story_shows_placeholder_for_empty_payload(tmp_path, monkeypatch):
    """_render_story must print 'No user story exists yet.' when payload has only user_id."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["story"])

    assert result.exit_code == 0
    assert "No user story exists yet." in result.output, (
        f"Expected placeholder message, got: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Bug 5 — drift table must use State/Signals columns, no hardcoded "-"
# isBugCondition_5: "Before" column rendered as hardcoded "-"
# ---------------------------------------------------------------------------

def test_bug5_drift_table_uses_state_and_signals_columns(tmp_path, monkeypatch):
    """soul drift must render 'State' and 'Signals' columns in chronological order."""
    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    personality_repo = PersonalityStateRepository(settings.database_url, user_id=settings.user_id)
    # Insert two drift rows in order
    personality_repo.record_state(
        {"curiosity": 0.6},
        resonance_signals={"signal_a": 0.5},
        notes="first run",
    )
    personality_repo.record_state(
        {"curiosity": 0.8},
        resonance_signals={"signal_b": 0.9},
        notes="second run",
    )

    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings, SimpleNamespace(name="Ara")))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["drift"])

    assert result.exit_code == 0
    assert "State" in result.output, "Table must have 'State' column"
    assert "Signals" in result.output, "Table must have 'Signals' column"
    assert "Before" not in result.output, "Old 'Before' column must not appear"

    # No hardcoded "-" as a standalone cell value
    lines = result.output.splitlines()
    data_lines = [ln for ln in lines if "curiosity" in ln or "signal" in ln]
    for line in data_lines:
        assert line.strip() != "-", f"Hardcoded '-' found in data line: {line!r}"

    # Chronological order: first run's state appears before second run's state
    idx_first = next((i for i, ln in enumerate(lines) if "signal_a" in ln), None)
    idx_second = next((i for i, ln in enumerate(lines) if "signal_b" in ln), None)
    if idx_first is not None and idx_second is not None:
        assert idx_first < idx_second, "Rows must be in chronological order (oldest first)"


# ---------------------------------------------------------------------------
# Bug 6 — get_last_companion_state must filter by user_id
# isBugCondition_6: query.user_id IS NOT NULL
# ---------------------------------------------------------------------------

def test_bug6_get_last_companion_state_filters_by_user(tmp_path):
    """get_last_companion_state(db, user_id='user-a') must return user-a's state only."""
    settings_a = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="user-a",
    )
    db.init_db(settings_a.database_url)

    messages_a = MessagesRepository(settings_a.database_url, user_id="user-a")
    messages_b = MessagesRepository(settings_a.database_url, user_id="user-b")

    session_a = messages_a.create_session("Ara")
    session_b = messages_b.create_session("Ara")

    # user-a gets companion_state "warm"
    messages_a.log_message(
        session_id=session_a,
        role="assistant",
        content="Hello user-a",
        companion_state="warm",
    )
    # user-b gets companion_state "curious" — inserted AFTER user-a so it would win without filter
    messages_b.log_message(
        session_id=session_b,
        role="assistant",
        content="Hello user-b",
        companion_state="curious",
    )

    state = db.get_last_companion_state(settings_a.database_url, user_id="user-a")
    assert state == "warm", (
        f"Expected 'warm' (user-a's state), got {state!r}. "
        "get_last_companion_state must filter by user_id."
    )


# ---------------------------------------------------------------------------
# Bug 7 — Connection must be importable from soul.db without NameError
# isBugCondition_7: Connection not in sqlalchemy.engine imports
# ---------------------------------------------------------------------------

def test_bug7_connection_importable_from_soul_db():
    """soul.db must expose Connection from sqlalchemy.engine without NameError."""
    import soul.db as soul_db
    import typing as _typing

    # Connection must be resolvable in the module namespace
    assert hasattr(soul_db, "Connection") or _connection_in_annotations(soul_db), (
        "Connection must be importable from soul.db"
    )

    # Verify _fetch_dicts annotation resolves without NameError
    hints = _typing.get_type_hints(soul_db._fetch_dicts)
    assert "connection" in hints, "_fetch_dicts must have a 'connection' type annotation"


def _connection_in_annotations(module) -> bool:  # noqa: ANN001
    """Check if Connection is accessible via the module's globals (used in annotations)."""
    return "Connection" in vars(module)


# ---------------------------------------------------------------------------
# Bug 8 — memories clear must only delete current user's memories
# isBugCondition_8: cmd = "memories clear"
# ---------------------------------------------------------------------------

def test_bug8_memories_clear_is_user_scoped(tmp_path, monkeypatch):
    """soul memories clear must not delete other users' memories."""
    settings_a = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="user-a",
    )
    db.init_db(settings_a.database_url)

    # Insert memories for user-a
    repo_a = EpisodicMemoryRepository(settings=settings_a)
    repo_a.add_text("user-a memory", importance=0.6)

    # Insert memories for user-b using a separate settings object
    settings_b = Settings(
        _env_file=None,
        database_url=settings_a.database_url,
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="user-b",
    )
    repo_b = EpisodicMemoryRepository(settings=settings_b)
    repo_b.add_text("user-b memory", importance=0.6)

    # Confirm both users have memories
    assert len(db.list_episodic_memories(settings_a.database_url, user_id="user-a")) == 1
    assert len(db.list_episodic_memories(settings_a.database_url, user_id="user-b")) == 1

    # Run memories clear as user-a
    monkeypatch.setattr(cli, "_bootstrap", lambda: (settings_a, SimpleNamespace(name="Ara")))
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *args, **kwargs: True))

    runner = CliRunner()
    result = runner.invoke(cli.app, ["memories", "clear"])

    assert result.exit_code == 0

    # user-a's memories must be gone
    assert db.list_episodic_memories(settings_a.database_url, user_id="user-a") == []
    # user-b's memories must still exist
    user_b_memories = db.list_episodic_memories(settings_a.database_url, user_id="user-b")
    assert len(user_b_memories) == 1, (
        f"user-b's memories must be intact after user-a clears theirs, got {user_b_memories}"
    )


# ---------------------------------------------------------------------------
# Bug 9a — MoodEngine must instantiate OpenAI client only once
# isBugCondition_9a: new OpenAI() instantiated inside _openai_mood
# ---------------------------------------------------------------------------

def test_bug9a_mood_engine_openai_client_instantiated_once(tmp_path):
    """MoodEngine must reuse a single OpenAI client across multiple analyze() calls."""
    from soul.core.mood_engine import MoodEngine

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    engine = MoodEngine(settings=settings)

    # Verify the caching infrastructure is in place
    assert hasattr(engine, "_openai_client"), "MoodEngine must have _openai_client attribute"
    assert engine._openai_client is None, "_openai_client must start as None (lazy init)"
    assert hasattr(engine, "_get_openai_client"), "MoodEngine must have _get_openai_client method"

    # Inject a pre-built mock client directly (bypasses API key check — we're testing caching, not auth)
    mock_client = MagicMock()
    engine._openai_client = mock_client

    # Calling _get_openai_client again must return the same cached instance without re-constructing
    client1 = engine._get_openai_client()
    client2 = engine._get_openai_client()

    assert client1 is mock_client, "_get_openai_client must return the pre-cached instance"
    assert client2 is mock_client, "_get_openai_client must return the same cached instance on repeated calls"
    assert client1 is client2, "Both calls must return the identical object"


def test_bug9a_openai_constructor_called_once_across_multiple_analyze_calls(tmp_path):
    """OpenAI() constructor must be called at most once across N analyze() calls."""
    from soul.core.mood_engine import MoodEngine
    from pydantic import SecretStr

    # Provide a fake API key so _get_openai_client passes the key guard
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

    constructor_calls = []

    class MockOpenAI:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            constructor_calls.append(1)
            self.chat = mock_client.chat

    # OpenAI is imported lazily inside _get_openai_client; patch at the openai module level
    with patch("openai.OpenAI", MockOpenAI):
        engine = MoodEngine(settings=settings)
        # _openai_client starts as None — first analyze() call triggers lazy init
        engine.analyze("first call", persist=False)
        engine.analyze("second call", persist=False)
        engine.analyze("third call", persist=False)

    assert len(constructor_calls) == 1, (
        f"OpenAI() constructor must be called exactly once, was called {len(constructor_calls)} times"
    )


# ---------------------------------------------------------------------------
# Bug 9b — analyze() must not mutate self.repository for cross-user calls
# isBugCondition_9b: call.user_id != self.settings.user_id AND self.repository mutated
# ---------------------------------------------------------------------------

def test_bug9b_analyze_does_not_mutate_self_repository(tmp_path):
    """analyze(user_id='b') must not reassign self.repository when engine is for user 'a'."""
    from soul.core.mood_engine import MoodEngine

    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="user-a",
    )
    db.init_db(settings.database_url)

    engine = MoodEngine(settings=settings)
    original_repo = engine.repository
    assert original_repo.user_id == "user-a"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"mood": "neutral", "confidence": 0.8}'
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(engine, "_get_openai_client", return_value=mock_client):
        engine.analyze("hello from user-b", user_id="user-b", persist=False)

    assert engine.repository is original_repo, (
        "self.repository must not be replaced after analyze(user_id='user-b')"
    )
    assert engine.repository.user_id == "user-a", (
        f"engine.repository.user_id must still be 'user-a', got {engine.repository.user_id!r}"
    )


# ---------------------------------------------------------------------------
# Bug 10a — consolidate_pending_sessions must continue after ExtractionValidationError
# isBugCondition_10: llm_response is NOT valid JSON
# ---------------------------------------------------------------------------

def test_bug10a_consolidation_continues_after_extraction_error(tmp_path, monkeypatch):
    """consolidate_pending_sessions must process all sessions even if one raises ExtractionValidationError."""
    from soul.bootstrap.errors import ExtractionValidationError
    from soul.maintenance.consolidation import consolidate_pending_sessions
    import soul.maintenance.consolidation as consolidation_mod

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    messages_repo = MessagesRepository(settings.database_url, user_id=settings.user_id)

    # Create two completed sessions with user messages
    session_1 = messages_repo.create_session("Ara")
    messages_repo.log_message(session_id=session_1, role="user", content="I am stressed about the deadline.")
    messages_repo.log_message(session_id=session_1, role="assistant", content="I hear you.")
    messages_repo.close_session(session_1)

    session_2 = messages_repo.create_session("Ara")
    messages_repo.log_message(session_id=session_2, role="user", content="I launched the product today!")
    messages_repo.log_message(session_id=session_2, role="assistant", content="That is wonderful.")
    messages_repo.close_session(session_2)

    call_count = 0

    def mock_extract(user_lines, resolved_settings):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ExtractionValidationError("Simulated bad JSON from LLM")
        from soul.maintenance.consolidation import StructuredSessionInsights
        return StructuredSessionInsights()

    monkeypatch.setattr(consolidation_mod, "_extract_structured_insights", mock_extract)

    results = consolidate_pending_sessions(database_url=settings.database_url, settings=settings)

    assert len(results) == 2, (
        f"Both sessions must be processed, got {len(results)} results"
    )
    processed_ids = {str(r["session_id"]) for r in results}
    assert session_1 in processed_ids, "session_1 must be in results"
    assert session_2 in processed_ids, "session_2 must be in results"


# ---------------------------------------------------------------------------
# Bug 10b — generate_monthly_reflection must return None on ExtractionValidationError
# isBugCondition_10: llm_response is NOT valid JSON
# ---------------------------------------------------------------------------

def test_bug10b_reflection_returns_none_on_parse_error(tmp_path, monkeypatch):
    """generate_monthly_reflection must return None (not raise) when _parse_reflection_response raises."""
    from soul.bootstrap.errors import ExtractionValidationError
    from soul.maintenance.reflection import generate_monthly_reflection
    import soul.maintenance.reflection as reflection_mod

    settings = _settings(tmp_path)
    db.init_db(settings.database_url)

    # Create the required soul.yaml so load_soul doesn't fail
    soul_data_dir = tmp_path / "soul_data"
    soul_data_dir.mkdir(parents=True, exist_ok=True)
    soul_yaml = soul_data_dir / "soul.yaml"
    soul_yaml.write_text(
        'identity:\n  name: "Ara"\n  voice: "warm"\n  energy: "steady"\ncharacter: {}\nethics: {}\nworldview: {}\n',
        encoding="utf-8",
    )

    def mock_parse(text):  # noqa: ANN001
        raise ExtractionValidationError("Simulated malformed JSON from LLM")

    # Mock the LLM call so we don't need a real API key
    mock_llm_result = MagicMock()
    mock_llm_result.text = "not valid json at all"

    monkeypatch.setattr(reflection_mod, "_parse_reflection_response", mock_parse)

    from soul.core.llm_client import LLMClient
    monkeypatch.setattr(LLMClient, "complete_text", lambda self, **kwargs: mock_llm_result)

    result = generate_monthly_reflection(settings=settings)

    assert result is None, (
        f"generate_monthly_reflection must return None on ExtractionValidationError, got {result!r}"
    )
