"""Repository for SQLite-backed user facts and story reconstruction."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from soul.bootstrap.errors import PersistenceError
from soul.memory.user_story import BigMoment, UserStory, ensure_story_defaults
from soul.persistence.db import connect, get_engine, utcnow_iso


class UserFactsRepository:
    def __init__(self, database: str | Path, *, user_id: str = "local-user"):
        self.database = database
        self.user_id = user_id

    def load_story(self) -> UserStory:
        story = ensure_story_defaults(UserStory(user_id=self.user_id))
        try:
            with connect(self.database) as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT fact_type, key, value, extra_json, observed_at
                        FROM user_facts
                        WHERE user_id = :user_id AND active = 1
                        ORDER BY observed_at ASC, created_at ASC
                        """
                    ),
                    {"user_id": self.user_id},
                ).mappings().all()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

        for row in rows:
            fact_type = str(row["fact_type"])
            key = str(row["key"])
            value = str(row["value"])
            extra = json.loads(str(row["extra_json"]))
            observed_at = str(row["observed_at"])
            if fact_type == "basic":
                story.basics[key] = value
            elif fact_type == "current_chapter":
                story.current_chapter[key] = value
            elif fact_type == "active_goal" and value not in story.current_chapter["active_goals"]:
                story.current_chapter["active_goals"].append(value)
            elif fact_type == "active_fear" and value not in story.current_chapter["active_fears"]:
                story.current_chapter["active_fears"].append(value)
            elif fact_type == "value" and value not in story.values_observed:
                story.values_observed.append(value)
            elif fact_type == "trigger" and value not in story.triggers:
                story.triggers.append(value)
            elif fact_type == "love" and value not in story.things_they_love:
                story.things_they_love.append(value)
            elif fact_type == "upcoming_event":
                event = {"date": key, "title": value, "notes": str(extra.get("notes", ""))}
                if event not in story.upcoming_events:
                    story.upcoming_events.append(event)
            elif fact_type == "relationship":
                relation = {"name": key, "role": value, "notes": str(extra.get("notes", ""))}
                if relation not in story.relationships:
                    story.relationships.append(relation)
            elif fact_type == "big_moment":
                story.big_moments.append(
                    BigMoment(
                        date=key or observed_at[:10],
                        event=value,
                        emotional_weight=str(extra.get("emotional_weight", "medium")),
                        companion_was_there=bool(extra.get("companion_was_there", True)),
                    )
                )
            story.updated_at = observed_at
        return story

    def load(self) -> UserStory:
        return self.load_story()

    def save_story(self, story: UserStory, *, source: str = "runtime") -> None:
        story = ensure_story_defaults(story)
        if not story.updated_at:
            story.updated_at = utcnow_iso()
        try:
            with get_engine(self.database).begin() as connection:
                connection.execute(text("DELETE FROM user_facts WHERE user_id = :user_id"), {"user_id": self.user_id})
                for key, value in story.basics.items():
                    if value:
                        self._insert_fact(connection, "basic", key, value, story.updated_at, source=source)
                for key in ("summary", "current_mood_trend"):
                    value = str(story.current_chapter.get(key, "") or "").strip()
                    if value:
                        self._insert_fact(connection, "current_chapter", key, value, story.updated_at, source=source)
                for value in story.current_chapter.get("active_goals", []):
                    self._insert_fact(connection, "active_goal", value, value, story.updated_at, source=source)
                for value in story.current_chapter.get("active_fears", []):
                    self._insert_fact(connection, "active_fear", value, value, story.updated_at, source=source)
                for value in story.values_observed:
                    self._insert_fact(connection, "value", value, value, story.updated_at, source=source)
                for value in story.triggers:
                    self._insert_fact(connection, "trigger", value, value, story.updated_at, source=source)
                for value in story.things_they_love:
                    self._insert_fact(connection, "love", value, value, story.updated_at, source=source)
                for item in story.upcoming_events:
                    self._insert_fact(
                        connection,
                        "upcoming_event",
                        str(item.get("date", "")),
                        str(item.get("title", "")),
                        story.updated_at,
                        source=source,
                        extra={"notes": str(item.get("notes", ""))},
                    )
                for item in story.relationships:
                    self._insert_fact(
                        connection,
                        "relationship",
                        str(item.get("name", "")),
                        str(item.get("role", "")),
                        story.updated_at,
                        source=source,
                        extra={"notes": str(item.get("notes", ""))},
                    )
                for item in story.big_moments:
                    self._insert_fact(
                        connection,
                        "big_moment",
                        item.date,
                        item.event,
                        story.updated_at,
                        source=source,
                        extra={
                            "emotional_weight": item.emotional_weight,
                            "companion_was_there": item.companion_was_there,
                        },
                    )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def save(self, story: UserStory, *, source: str = "runtime") -> None:
        self.save_story(story, source=source)

    def export_story_payload(self) -> dict[str, object]:
        return asdict(self.load_story())

    def import_story_payload(self, payload: dict[str, object], *, source: str = "story_edit") -> UserStory:
        story = UserStory(**payload)
        story.big_moments = [item if isinstance(item, BigMoment) else BigMoment(**item) for item in story.big_moments]
        self.save_story(story, source=source)
        return story

    def _insert_fact(
        self,
        connection,  # type: ignore[no-untyped-def]
        fact_type: str,
        key: str,
        value: str,
        observed_at: str,
        *,
        source: str,
        extra: dict[str, object] | None = None,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO user_facts (
                    id, user_id, fact_type, key, value, extra_json, score, source, observed_at, created_at, updated_at, active
                )
                VALUES (
                    :id, :user_id, :fact_type, :key, :value, :extra_json, :score, :source, :observed_at, :created_at, :updated_at, :active
                )
                """
            ),
            {
                "id": str(uuid4()),
                "user_id": self.user_id,
                "fact_type": fact_type,
                "key": key,
                "value": value,
                "extra_json": json.dumps(extra or {}, ensure_ascii=True),
                "score": 1.0,
                "source": source,
                "observed_at": observed_at,
                "created_at": observed_at,
                "updated_at": observed_at,
                "active": 1,
            },
        )
