from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Memory:
    id: str
    user_id: str
    session_id: str
    timestamp: str
    content: str
    emotional_tag: str | None = None
    importance: float = 0.5
    memory_type: str = "moment"
    word_count: int = 0
    flagged: bool = False
    ref_count: int = 0
    tier: str = "present"
    hms_score: float = 0.5
