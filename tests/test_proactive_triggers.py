from __future__ import annotations

from datetime import datetime, timezone

from soul.memory.user_story import UserStory
from soul.tasks.proactive import build_reach_out_candidates


def test_build_reach_out_candidates_emits_all_required_triggers():
    today = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)  # Monday
    story = UserStory(
        basics={"birthday": "2000-03-16"},
        current_chapter={"summary": "steady"},
        upcoming_events=[{"date": "2026-03-18", "title": "investor meeting", "notes": ""}],
    )

    candidates = build_reach_out_candidates(
        days_since_last_chat=3,
        story=story,
        today=today,
        stress_signal_dates=["2026-03-13T12:00:00+00:00"],
        milestones_today=["1-month anniversary"],
    )

    triggers = {item.trigger for item in candidates}
    assert {
        "silence_3_days",
        "monday_morning",
        "past_stress_3d",
        "upcoming_event",
        "milestone_today",
        "birthday",
    } <= triggers


def test_past_stress_trigger_requires_dated_signal_not_only_story_mood():
    today = datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc)
    story = UserStory(current_chapter={"current_mood_trend": "stressed"})

    candidates = build_reach_out_candidates(
        days_since_last_chat=0,
        story=story,
        today=today,
        stress_signal_dates=[],
    )

    triggers = {item.trigger for item in candidates}
    assert "past_stress_3d" not in triggers


def test_birthday_trigger_supports_month_day_leap_day_format():
    today = datetime(2024, 2, 29, 9, 0, tzinfo=timezone.utc)
    story = UserStory(basics={"birthday": "02-29"})

    candidates = build_reach_out_candidates(
        days_since_last_chat=0,
        story=story,
        today=today,
    )

    triggers = {item.trigger for item in candidates}
    assert "birthday" in triggers
