from __future__ import annotations

import json


USER_STORY_FIXTURE = """
{
  "user_id": "uuid",
  "updated_at": "2026-03-19T00:00:00Z",
  "basics": {
    "name": "Asha",
    "location": "Chennai",
    "occupation": "founder",
    "birthday": "1995-03-19"
  },
  "current_chapter": {
    "summary": "Working on a startup, feeling pressure from investors.",
    "active_goals": ["launch MVP by June", "find a co-founder"],
    "active_fears": ["running out of runway", "impostor syndrome"],
    "current_mood_trend": "driven but tired"
  },
  "big_moments": [
    {
      "date": "2026-01-14",
      "event": "Quit their job to go full-time on the startup",
      "emotional_weight": "high",
      "companion_was_there": true
    }
  ],
  "upcoming_events": [
    { "date": "2026-03-25", "title": "Investor meeting", "notes": "Series A prep" }
  ],
  "relationships": [
    { "name": "Priya", "role": "best friend", "notes": "going through a breakup" }
  ],
  "values_observed": ["independence", "creativity", "loyalty"],
  "triggers": ["dismissive tone", "being talked down to"],
  "things_they_love": ["lo-fi music", "late night coding", "Tamil cinema"]
}
"""

REQUIRED_TOP_LEVEL_KEYS = {
    "user_id",
    "updated_at",
    "basics",
    "current_chapter",
    "big_moments",
    "upcoming_events",
    "relationships",
    "values_observed",
    "triggers",
    "things_they_love",
}


def test_user_story_fixture_has_expected_top_level_shape():
    story = json.loads(USER_STORY_FIXTURE)

    assert REQUIRED_TOP_LEVEL_KEYS <= set(story)
    assert story["current_chapter"]["summary"].startswith("Working on a startup")
    assert story["big_moments"][0]["companion_was_there"] is True
    assert story["basics"]["birthday"] == "1995-03-19"


def test_user_story_lists_are_json_friendly():
    story = json.loads(USER_STORY_FIXTURE)

    assert isinstance(story["relationships"], list)
    assert isinstance(story["upcoming_events"], list)
    assert isinstance(story["values_observed"], list)
    assert isinstance(story["triggers"], list)
