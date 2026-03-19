from __future__ import annotations

from datetime import datetime, timedelta, timezone

from soul import db
from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.evolution.milestone_tracker import Milestone, MilestoneTracker
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.shared_language import SharedLanguageStore
from soul.memory.user_story import UserStoryRepository, apply_story_observations


class PostProcessor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.story_repo = UserStoryRepository(settings.user_story_file)
        self.episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)
        self.shared_language = SharedLanguageStore(settings.shared_language_file)
        self.milestones = MilestoneTracker(settings.milestones_file)

    def process_turn(self, *, session_id: str, user_text: str, assistant_text: str, mood: MoodSnapshot) -> None:
        story_update = self._update_story(user_text, mood)
        recurring_phrases = self._update_shared_language(user_text)
        self._track_milestones(
            session_id=session_id,
            user_text=user_text,
            mood=mood,
            big_moment_event=story_update.get("big_moment_event"),
            recurring_phrases=recurring_phrases,
        )

        if mood.user_mood in {"venting", "reflective", "celebrating"} and len(user_text.split()) >= 8:
            self.episodic_repo.add_text(
                user_text,
                emotional_tag=mood.user_mood,
                importance=0.65,
                memory_type="moment",
                metadata={
                    "session_id": session_id,
                    "user_id": self.settings.user_id,
                    "timestamp": db.utcnow_iso(),
                },
            )
            db.save_memory(
                self.settings.database_url,
                session_id=session_id,
                label=f"{mood.user_mood} moment",
                content=user_text,
                importance=0.65,
                source="auto",
            )

    def process_session_end(self, *, session_id: str) -> None:
        rows = db.get_session_messages(self.settings.database_url, session_id)
        user_rows = [row for row in rows if str(row.get("role", "")).casefold() == "user" and str(row.get("content", "")).strip()]
        export_state = db.get_session_memory_export_state(self.settings.database_url, session_id) or {}
        exported_user_count = int(export_state.get("exported_user_count") or 0)
        if not user_rows:
            db.mark_session_memory_exported(self.settings.database_url, session_id, exported_user_count=0)
            return

        pending_user_rows = user_rows[exported_user_count:]
        if not pending_user_rows:
            return

        for chunk in self._chunk_rows(pending_user_rows, size=3):
            content = " ".join(str(row["content"]).strip() for row in chunk if str(row.get("content", "")).strip()).strip()
            if not content:
                continue
            timestamp = str(chunk[-1].get("created_at") or db.utcnow_iso())
            dominant_mood = self._dominant_user_mood(chunk)
            importance = min(0.85, round(0.55 + min(0.2, len(content.split()) / 200), 2))
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
                },
            )
            db.save_memory(
                self.settings.database_url,
                session_id=session_id,
                label="session memory chunk",
                content=content,
                importance=importance,
                source="session_end",
            )
        db.mark_session_memory_exported(
            self.settings.database_url,
            session_id,
            exported_user_count=len(user_rows),
        )

    def _track_milestones(
        self,
        *,
        session_id: str,
        user_text: str,
        mood: MoodSnapshot,
        big_moment_event: str | None,
        recurring_phrases: list[str],
    ) -> None:
        if db.count_sessions(self.settings.database_url) == 1 and not db.milestone_exists(
            self.settings.database_url, "first_conversation"
        ):
            self._record_db_milestone(
                kind="first_conversation",
                note="First conversation ever.",
                session_id=session_id,
                title="First conversation ever",
                description="The relationship started.",
                category="relationship",
            )

        if db.count_messages(self.settings.database_url, role="user") >= 100 and not db.milestone_exists(
            self.settings.database_url, "hundredth_message"
        ):
            self._record_db_milestone(
                kind="hundredth_message",
                note="Reached 100 user messages.",
                session_id=session_id,
                title="100th message",
                description="Reached 100 user messages.",
                category="relationship",
            )

        vulnerable = mood.user_mood in {"venting", "overwhelmed", "stressed"} or any(
            phrase in user_text.casefold()
            for phrase in ("i'm scared", "i am scared", "i feel invisible", "i feel alone", "i feel broken")
        )
        if vulnerable and not db.milestone_exists(self.settings.database_url, "first_vulnerable_share"):
            self._record_db_milestone(
                kind="first_vulnerable_share",
                note="First vulnerable share detected.",
                session_id=session_id,
                title="First vulnerable share",
                description="The user shared something emotionally exposed.",
                category="emotional",
            )

        if recurring_phrases and not db.milestone_exists(self.settings.database_url, "first_recurring_phrase"):
            phrase = recurring_phrases[0]
            self._record_db_milestone(
                kind="first_recurring_phrase",
                note=f'First recurring phrase detected: "{phrase}".',
                session_id=session_id,
                title="First recurring phrase",
                description=f'The relationship developed a shared phrase: "{phrase}".',
                category="memory",
            )

        if self._has_conversation_streak(7) and not db.milestone_exists(self.settings.database_url, "seven_day_streak"):
            self._record_db_milestone(
                kind="seven_day_streak",
                note="Reached a 7-day conversation streak.",
                session_id=session_id,
                title="7-day conversation streak",
                description="The conversation has continued for seven consecutive days.",
                category="relationship",
            )

        if self._has_anniversary(days=30) and not db.milestone_exists(self.settings.database_url, "one_month_anniversary"):
            self._record_db_milestone(
                kind="one_month_anniversary",
                note="Reached the 1-month anniversary.",
                session_id=session_id,
                title="1-month anniversary",
                description="A month has passed since the first conversation.",
                category="relationship",
            )

        if self._has_anniversary(days=90) and not db.milestone_exists(self.settings.database_url, "three_month_anniversary"):
            self._record_db_milestone(
                kind="three_month_anniversary",
                note="Reached the 3-month anniversary.",
                session_id=session_id,
                title="3-month anniversary",
                description="Three months have passed since the first conversation.",
                category="relationship",
            )

        if big_moment_event:
            milestone_kind = f"major_life_event_{self._slugify(big_moment_event)[:48]}"
            if not db.milestone_exists(self.settings.database_url, milestone_kind):
                self._record_db_milestone(
                    kind=milestone_kind,
                    note=f"Major life event: {big_moment_event}",
                    session_id=session_id,
                    title="Major life event",
                    description=big_moment_event,
                    category="story",
                )

    def _update_story(self, user_text: str, mood: MoodSnapshot) -> dict[str, str | None]:
        story = self.story_repo.load()
        if not story.user_id or story.user_id in ("unknown", ""):
            story.user_id = self.settings.user_id
        update = apply_story_observations(
            story,
            [user_text],
            mood_hint=mood.user_mood,
            observed_at=db.utcnow_iso(),
        )
        self.story_repo.save(story)
        return {"big_moment_event": update.big_moment.event if update.big_moment else None}

    def _update_shared_language(self, user_text: str) -> list[str]:
        lowered = user_text.casefold()
        recurring: list[str] = []
        if "as always" in lowered:
            entry = self.shared_language.register("as always", "recurring reassurance")
            if entry.count == 2:
                recurring.append(entry.phrase)
        if "late night coding" in lowered:
            entry = self.shared_language.register("late night coding", "favorite ritual")
            if entry.count == 2:
                recurring.append(entry.phrase)
        if "rough day" in lowered:
            entry = self.shared_language.register("rough day", "shared shorthand for a hard day")
            if entry.count == 2:
                recurring.append(entry.phrase)
        return recurring

    def _record_db_milestone(
        self,
        *,
        kind: str,
        note: str,
        session_id: str,
        title: str,
        description: str,
        category: str,
    ) -> None:
        db.insert_milestone(
            self.settings.database_url,
            kind=kind,
            note=note,
            session_id=session_id,
        )
        self._record_milestone(title, description, category)

    def _record_milestone(self, title: str, description: str, category: str) -> None:
        existing = {(item.title, item.description) for item in self.milestones.load()}
        if (title, description) in existing:
            return
        self.milestones.record(
            Milestone(
                date=datetime.now(timezone.utc).date().isoformat(),
                title=title,
                description=description,
                category=category,
            )
        )

    def _has_conversation_streak(self, length: int) -> bool:
        sessions = db.list_sessions(self.settings.database_url)
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
        sessions = db.list_sessions(self.settings.database_url, limit=1)
        if not sessions:
            return False
        first_date = datetime.fromisoformat(str(sessions[0]["started_at"])).date()
        today = datetime.now(timezone.utc).date()
        if first_date == today:
            return False
        return (today - first_date).days >= days

    def _slugify(self, value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "_" for char in value)
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug.strip("_") or "event"

    def _chunk_rows(self, rows: list[dict[str, object]], *, size: int) -> list[list[dict[str, object]]]:
        chunks: list[list[dict[str, object]]] = []
        for index in range(0, len(rows), size):
            chunk = rows[index : index + size]
            if chunk:
                chunks.append(chunk)
        return chunks

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
