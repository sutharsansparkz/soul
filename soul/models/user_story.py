from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class UserStoryProfile:
    user_id: str = "unknown"
    updated_at: str = ""
    basics: dict[str, str] = field(default_factory=dict)
    current_chapter: dict[str, object] = field(default_factory=dict)
    big_moments: list[dict[str, object]] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)
    values_observed: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    things_they_love: list[str] = field(default_factory=list)

