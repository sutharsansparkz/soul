from __future__ import annotations

from dataclasses import dataclass

from soul.config import Settings
from soul.core.soul_loader import Soul, compile_system_prompt
from soul.core.mood_engine import MoodSnapshot
from soul.memory.episodic import EpisodicMemoryRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.memory.repositories.user_facts import UserFactsRepository
from soul.memory.vector_store import MemoryRecord
from soul.memory.vector_store import format_memory_blocks


@dataclass(slots=True)
class ContextBundle:
    system_prompt: str
    messages: list[dict[str, str]]
    story_summary: str | None
    memory_snippets: list[str]
    retrieved_memories: list[MemoryRecord]
    prompt_sections: list[str]


class ContextBuilder:
    def __init__(self, settings: Settings, soul: Soul) -> None:
        self.settings = settings
        self.soul = soul
        self.messages = MessagesRepository(settings.database_url, user_id=settings.user_id)
        self.story_repo = UserFactsRepository(settings.database_url, user_id=settings.user_id)
        self.personality_repo = PersonalityStateRepository(settings.database_url, user_id=settings.user_id)
        self.episodic_repo = EpisodicMemoryRepository(settings=settings)

    def build(self, *, session_id: str, user_input: str, mood: MoodSnapshot) -> ContextBundle:
        recent_messages = self.messages.get_recent_session_messages(
            session_id,
            limit=self.settings.context_history_limit,
        )
        story_summary = self._story_summary()
        personality_hint = self._personality_context()
        retrieved_memories = self._retrieve_memories(user_input)
        memory_snippets = format_memory_blocks(retrieved_memories[: self.settings.memory_retrieval_k])
        prompt_sections = ["mood", "soul_prompt"]

        system_parts = [
            f"[user_mood: {mood.user_mood}]",
            f"[companion_state: {mood.companion_state}]",
            "Read the emotional context before you answer.",
            "",
            compile_system_prompt(self.soul),
        ]
        if story_summary:
            prompt_sections.append("story")
            system_parts.extend(["", "[user_story]", story_summary])
        if personality_hint:
            prompt_sections.append("personality")
            system_parts.extend(["", "[personality_drift]", personality_hint])
        if memory_snippets:
            prompt_sections.append("memory")
            system_parts.extend(["", "[memory_context]"])
            system_parts.extend(memory_snippets)

        messages = [{"role": str(row["role"]), "content": str(row["content"])} for row in recent_messages]
        messages.append({"role": "user", "content": user_input})

        return ContextBundle(
            system_prompt="\n".join(system_parts).strip(),
            messages=messages,
            story_summary=story_summary,
            memory_snippets=memory_snippets,
            retrieved_memories=retrieved_memories,
            prompt_sections=prompt_sections,
        )

    def _story_summary(self) -> str | None:
        story = self.story_repo.load_story()
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

    def _personality_context(self) -> str | None:
        dims = self.personality_repo.get_current_state()
        if not dims:
            return None
        dimension_hints: dict[str, tuple[str, str]] = {
            "humor_intensity": ("serious and measured", "playful, witty, light"),
            "response_length": ("terse and brief", "expansive and thorough"),
            "curiosity_depth": ("surface-level questions", "deep, probing follow-ups"),
            "directness": ("gentle and indirect", "blunt and plain-spoken"),
            "warmth_expression": ("reserved and contained", "openly warm and affectionate"),
        }
        baseline = self.settings.personality_drift_baseline
        threshold = self.settings.personality_drift_render_threshold
        lines: list[str] = []
        for dim, value in dims.items():
            if dim not in dimension_hints:
                continue
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            delta = score - baseline
            if abs(delta) < threshold:
                continue
            low_end, high_end = dimension_hints[dim]
            label = dim.replace("_", " ")
            if delta > 0:
                lines.append(f"- {label}: lean toward {high_end} (score {score:.2f})")
            else:
                lines.append(f"- {label}: lean toward {low_end} (score {score:.2f})")
        if not lines:
            return None
        return "Your current personality drift:\n" + "\n".join(lines)

    def _retrieve_memories(self, query: str) -> list[MemoryRecord]:
        return self.episodic_repo.retrieve(
            query=query,
            user_id=self.settings.user_id,
            k=self.settings.memory_retrieval_k,
            passive=True,
        )
