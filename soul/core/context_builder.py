from __future__ import annotations

from dataclasses import dataclass

from soul import db
from soul.config import Settings
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul, compile_system_prompt
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.user_story import UserStoryRepository
from soul.memory.vector_store import format_memory_blocks


@dataclass(slots=True)
class ContextBundle:
    system_prompt: str
    messages: list[dict[str, str]]
    story_summary: str | None
    memory_snippets: list[str]


class ContextBuilder:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.settings = settings
        self.soul = soul
        self.story_repo = UserStoryRepository(settings.user_story_file)
        self.episodic_repo = EpisodicMemoryRepository(settings.episodic_memory_file, settings=settings)

    def build(self, *, session_id: str, user_input: str, mood: MoodSnapshot) -> ContextBundle:
        recent_messages = db.get_recent_session_messages(self.settings.database_url, session_id, limit=12)
        story_summary = self._story_summary()
        memory_snippets = self._memory_context(user_input)

        system_parts = [
            f"[user_mood: {mood.user_mood}]",
            f"[companion_state: {mood.companion_state}]",
            "Read the emotional context before you answer.",
            "",
            compile_system_prompt(self.soul),
        ]
        if story_summary:
            system_parts.extend(["", "[user_story]", story_summary])
        if memory_snippets:
            system_parts.extend(["", "[memory_context]"])
            system_parts.extend(memory_snippets)

        messages = [{"role": row["role"], "content": str(row["content"])} for row in recent_messages]
        messages.append({"role": "user", "content": user_input})

        return ContextBundle(
            system_prompt="\n".join(system_parts).strip(),
            messages=messages,
            story_summary=story_summary,
            memory_snippets=memory_snippets,
        )

    def _story_summary(self) -> str | None:
        story = self.story_repo.load()
        parts: list[str] = []
        if story.basics:
            bits = ", ".join(f"{key}: {value}" for key, value in story.basics.items() if value)
            if bits:
                parts.append(f"Basics: {bits}")
        if story.current_chapter:
            summary = story.current_chapter.get("summary")
            if summary:
                parts.append(f"Current chapter: {summary}")
            mood = story.current_chapter.get("current_mood_trend")
            if mood:
                parts.append(f"Mood trend: {mood}")
        if story.values_observed:
            parts.append(f"Observed values: {', '.join(story.values_observed)}")
        if story.things_they_love:
            parts.append(f"Things they love: {', '.join(story.things_they_love)}")
        return "\n".join(parts) if parts else None

    def _memory_context(self, query: str) -> list[str]:
        episodic = self.episodic_repo.retrieve(
            query=query,
            user_id=self.settings.user_id,
            k=self.settings.memory_retrieval_k,
            passive=True,
        )
        if episodic:
            return format_memory_blocks(episodic[: self.settings.memory_retrieval_k])

        fallback = db.search_memories(self.settings.database_url, query=query, limit=self.settings.memory_retrieval_k)
        return [f"[memory:manual] {item['label']}: {item['content']}" for item in fallback[: self.settings.memory_retrieval_k]]
