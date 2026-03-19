from __future__ import annotations

import json

from soul import db
from soul.config import Settings
from soul.memory.shared_language import SharedLanguageStore
from soul.tasks.consolidate import consolidate_day, consolidate_lines


def test_consolidate_day_merges_structured_story_state_without_duplication(tmp_path):
    session_log = tmp_path / "latest_session.log"
    story_path = tmp_path / "user_story.json"
    memory_path = tmp_path / "episodic_memory.jsonl"
    shared_path = tmp_path / "shared_language.json"
    ledger_path = tmp_path / "consolidation_ledger.json"
    session_log.write_text(
        "\n".join(
            [
                "user: My name is Sam.",
                "assistant: Tell me more.",
                "user: I live in Chennai.",
                "assistant: Keep going.",
                "user: I work as a designer.",
                "assistant: Keep going.",
                "user: I love late night coding and I want to launch the beta.",
                "assistant: That sounds important.",
                "user: Priya is my best friend and I feel invisible after I launched the beta.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    first = consolidate_day(
        session_log,
        story_path,
        memory_path,
        shared_path,
        dedupe_key="session-1",
        ledger_path=ledger_path,
    )
    second = consolidate_day(
        session_log,
        story_path,
        memory_path,
        shared_path,
        dedupe_key="session-1",
        ledger_path=ledger_path,
    )

    story = json.loads(story_path.read_text(encoding="utf-8"))
    shared_entries = SharedLanguageStore(shared_path).load()

    assert first.story_updated is True
    assert first.memories_added >= 1
    assert second.skipped is True
    assert story["basics"]["name"] == "Sam"
    assert story["basics"]["location"] == "Chennai"
    assert story["basics"]["occupation"] == "a designer"
    assert story["things_they_love"] == ["late night coding and I want to launch the beta"]
    assert story["values_observed"] == []
    assert story["relationships"] == [{"name": "Priya", "role": "best friend", "notes": ""}]
    assert len(story["big_moments"]) == 1
    assert shared_entries[0].phrase == "late night coding"
    assert shared_entries[0].count == 1


def test_consolidate_lines_uses_provided_settings_for_memory_writes(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        user_id="audit-user",
    )
    db.init_db(settings.database_url)

    result = consolidate_lines(
        [
            "user: I launched the beta and felt stressed about the runway.",
            "assistant: Tell me more.",
        ],
        story_path=tmp_path / "user_story.json",
        memory_path=tmp_path / "episodic_memory.jsonl",
        settings=settings,
    )

    assert result.memories_added >= 1
    rows = db.list_episodic_memories(settings.database_url, user_id=settings.user_id, include_cold=True, limit=20)
    assert rows
