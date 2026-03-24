from __future__ import annotations

from datetime import datetime, timedelta, timezone

from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.milestones import MilestonesRepository
from soul.memory.repositories.shared_language import SharedLanguageRepository
from soul.memory.repositories.user_facts import UserFactsRepository
from soul.memory.user_story import apply_story_observations
from soul.persistence.db import utcnow_iso


class PostProcessor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.messages = MessagesRepository(settings.database_url, user_id=settings.user_id)
        self.story_repo = UserFactsRepository(settings.database_url, user_id=settings.user_id)
        self.episodic_repo = EpisodicMemoryRepository(settings=settings)
        self.shared_language = SharedLanguageRepository(settings.database_url, user_id=settings.user_id)
        self.milestones = MilestonesRepository(settings.database_url)

    def process_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        mood: MoodSnapshot,
    ) -> dict[str, object]:
        del assistant_text
        story_update = self._update_story(user_text, mood)
        recurring_phrases = self._update_shared_language(user_text)
        milestone_records = self._track_milestones(
            session_id=session_id,
            user_text=user_text,
            mood=mood,
            big_moment_event=story_update.get("big_moment_event"),
            recurring_phrases=recurring_phrases,
        )
        memory_id: str | None = None
        if mood.user_mood in set(self.settings.auto_memory_capture_moods) and len(user_text.split()) >= self.settings.auto_memory_min_words:
            record = self.episodic_repo.add_text(
                user_text,
                emotional_tag=mood.user_mood,
                importance=self.settings.auto_memory_importance,
                memory_type="moment",
                metadata={
                    "session_id": session_id,
                    "user_id": self.settings.user_id,
                    "timestamp": utcnow_iso(),
                    "source": "auto",
                    "label": f"{mood.user_mood} moment",
                },
            )
            memory_id = str(record.metadata.get("memory_id", record.id))
        return {
            "story_update": story_update,
            "shared_language": recurring_phrases,
            "milestones": milestone_records,
            "persisted_records": {
                "auto_memory_id": memory_id,
            },
        }

    def process_session_end(self, *, session_id: str) -> None:
        rows = self.messages.get_session_messages(session_id)
        user_rows = [
            row
            for row in rows
            if str(row.get("role", "")).casefold() == "user"
            and str(row.get("content", "")).strip()
            and self._should_export_user_row(row)
        ]
        export_state = self.messages.get_session_memory_export_state(session_id) or {}
        exported_user_count = int(export_state.get("exported_user_count") or 0)
        if not user_rows:
            self.messages.mark_session_memory_exported(session_id, exported_user_count=0)
            return

        pending_user_rows = user_rows[exported_user_count:]
        if not pending_user_rows:
            return

        fresh_state = self.messages.get_session_memory_export_state(session_id) or {}
        fresh_count = int(fresh_state.get("exported_user_count") or 0)
        if fresh_count != exported_user_count:
            return

        for chunk in self._chunk_rows(pending_user_rows, size=self.settings.session_memory_chunk_size):
            content = " ".join(str(row["content"]).strip() for row in chunk if str(row.get("content", "")).strip()).strip()
            if not content:
                continue
            timestamp = str(chunk[-1].get("created_at") or utcnow_iso())
            dominant_mood = self._dominant_user_mood(chunk)
            importance = min(
                self.settings.session_memory_max_importance,
                round(
                    self.settings.session_memory_base_importance
                    + min(
                        self.settings.session_memory_word_importance_cap,
                        len(content.split()) / self.settings.session_memory_word_importance_divisor,
                    ),
                    2,
                ),
            )
            self.episodic_repo.add_text(
                content,
                emotional_tag=dominant_mood,
                importance=importance,
                memory_type="moment",
                metadata={
                    "timestamp": timestamp,
                    "session_id": session_id,
                    "source": "session_end",
                    "user_id": self.settings.user_id,
                    "label": "session memory chunk",
                },
            )
        self.messages.mark_session_memory_exported(session_id, exported_user_count=len(user_rows))

    def _track_milestones(
        self,
        *,
        session_id: str,
        user_text: str,
        mood: MoodSnapshot,
        big_moment_event: str | None,
        recurring_phrases: list[str],
    ) -> list[dict[str, str]]:
        created: list[dict[str, str]] = []

        def _record(**kwargs: object) -> None:
            milestone_id = self.milestones.record(
                kind=str(kwargs["kind"]),
                note=str(kwargs["note"]),
                session_id=session_id,
                title=str(kwargs.get("title") or kwargs["kind"]),
                description=str(kwargs.get("description") or kwargs["note"]),
                category=str(kwargs.get("category") or "relationship"),
            )
            created.append(
                {
                    "id": milestone_id,
                    "kind": str(kwargs["kind"]),
                    "title": str(kwargs.get("title") or kwargs["kind"]),
                }
            )

        if self.messages.count_sessions() == 1 and not self.milestones.exists("first_conversation"):
            _record(
                kind="first_conversation",
                note="First conversation ever.",
                title="First conversation ever",
                description="The relationship started.",
                category="relationship",
            )

        if self.messages.count_messages(role="user") >= self.settings.milestone_message_count and not self.milestones.exists("hundredth_message"):
            _record(
                kind="hundredth_message",
                note=f"Reached {self.settings.milestone_message_count} user messages.",
                title=self._message_milestone_label(self.settings.milestone_message_count),
                description=f"Reached {self.settings.milestone_message_count} user messages.",
                category="relationship",
            )

        vulnerable = mood.user_mood in {"venting", "overwhelmed", "stressed"} or any(
            phrase in user_text.casefold() for phrase in self.settings.vulnerability_trigger_phrases
        )
        if vulnerable and not self.milestones.exists("first_vulnerable_share"):
            _record(
                kind="first_vulnerable_share",
                note="First vulnerable share detected.",
                title="First vulnerable share",
                description="The user shared something emotionally exposed.",
                category="emotional",
            )

        if recurring_phrases and not self.milestones.exists("first_recurring_phrase"):
            phrase = recurring_phrases[0]
            _record(
                kind="first_recurring_phrase",
                note=f'First recurring phrase detected: "{phrase}".',
                title="First recurring phrase",
                description=f'The relationship developed a shared phrase: "{phrase}".',
                category="memory",
            )

        if self._has_conversation_streak(self.settings.milestone_streak_days) and not self.milestones.exists("seven_day_streak"):
            _record(
                kind="seven_day_streak",
                note=f"Reached a {self.settings.milestone_streak_days}-day conversation streak.",
                title=f"{self.settings.milestone_streak_days}-day conversation streak",
                description=f"The conversation has continued for {self.settings.milestone_streak_days} consecutive days.",
                category="relationship",
            )

        if self._has_anniversary(days=self.settings.milestone_one_month_days) and not self.milestones.exists("one_month_anniversary"):
            _record(
                kind="one_month_anniversary",
                note="Reached the 1-month anniversary.",
                title="1-month anniversary",
                description="A month has passed since the first conversation.",
                category="relationship",
            )

        if self._has_anniversary(days=self.settings.milestone_three_month_days) and not self.milestones.exists("three_month_anniversary"):
            _record(
                kind="three_month_anniversary",
                note="Reached the 3-month anniversary.",
                title="3-month anniversary",
                description="Three months have passed since the first conversation.",
                category="relationship",
            )

        if big_moment_event:
            milestone_kind = f"major_life_event_{self._slugify(big_moment_event)[:48]}"
            if not self.milestones.exists(milestone_kind):
                _record(
                    kind=milestone_kind,
                    note=f"Major life event: {big_moment_event}",
                    title="Major life event",
                    description=big_moment_event,
                    category="story",
                )
        return created

    def _update_story(self, user_text: str, mood: MoodSnapshot) -> dict[str, object]:
        story = self.story_repo.load_story()
        if not story.user_id or story.user_id in ("unknown", ""):
            story.user_id = self.settings.user_id
        update = apply_story_observations(
            story,
            [user_text],
            mood_hint=mood.user_mood,
            observed_at=utcnow_iso(),
        )
        self.story_repo.save_story(story)
        return {
            "changed": update.changed,
            "big_moment_event": update.big_moment.event if update.big_moment else None,
        }

    def _update_shared_language(self, user_text: str) -> list[str]:
        lowered = user_text.casefold()
        recurring: list[str] = []
        for phrase, meaning in self.settings.shared_language_triggers.items():
            if phrase not in lowered:
                continue
            entry = self.shared_language.register(phrase, meaning)
            if entry.count == 2:
                recurring.append(entry.phrase)
        return recurring

    def _has_conversation_streak(self, length: int) -> bool:
        sessions = self.messages.list_sessions()
        days = sorted(
            {
                datetime.fromisoformat(str(session["started_at"])).date()
                for session in sessions
                if session.get("started_at")
            }
        )
        if len(days) < length:
            return False
        recent = days[-length:]
        if len(set(recent)) < length:
            return False
        return all((recent[index] - recent[index - 1]) == timedelta(days=1) for index in range(1, len(recent)))

    def _has_anniversary(self, *, days: int) -> bool:
        sessions = self.messages.list_sessions()
        if not sessions:
            return False
        first_started_at = min(str(session["started_at"]) for session in sessions if session.get("started_at"))
        first_date = datetime.fromisoformat(first_started_at).date()
        today = datetime.now(timezone.utc).date()
        if first_date == today:
            return False
        return (today - first_date).days >= days

    def _slugify(self, value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "_" for char in value)
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug.strip("_") or "event"

    def _message_milestone_label(self, count: int) -> str:
        if count == 100:
            return "100th message"
        return f"{count}-message milestone"

    def _should_export_user_row(self, row: dict[str, object]) -> bool:
        import json

        try:
            payload = json.loads(str(row.get("metadata_json") or "{}"))
        except json.JSONDecodeError:
            return True
        return not bool(payload.get("skip_memory"))

    def _chunk_rows(self, rows: list[dict[str, object]], *, size: int) -> list[list[dict[str, object]]]:
        if size <= 0:
            return [rows]
        return [rows[index : index + size] for index in range(0, len(rows), size)]

    def _dominant_user_mood(self, rows: list[dict[str, object]]) -> str | None:
        counts: dict[str, int] = {}
        for row in rows:
            mood = str(row.get("user_mood") or "").strip()
            if not mood:
                continue
            counts[mood] = counts.get(mood, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]
