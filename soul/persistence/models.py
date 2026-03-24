"""Canonical SQLite entity names for the single-user runtime."""

from __future__ import annotations

from dataclasses import dataclass


CANONICAL_TABLES = (
    "users",
    "sessions",
    "messages",
    "mood_snapshots",
    "user_facts",
    "episodic_memories",
    "shared_language_entries",
    "milestones",
    "personality_state",
    "reflection_artifacts",
    "proactive_candidates",
    "maintenance_runs",
    "turn_traces",
    "app_settings",
)


@dataclass(slots=True)
class TurnTraceRow:
    id: str
    session_id: str
    input_message_id: str | None
    reply_message_id: str | None
    status: str
    created_at: str
