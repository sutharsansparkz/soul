from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MemoryScore:
    memory_id: str
    user_id: str
    score_emotional: float = 0.5
    score_retrieval: float = 0.0
    score_temporal: float = 1.0
    score_flagged: float = 0.0
    score_volume: float = 0.3
    hms_score: float = 0.5
    last_computed: str = ""
    last_retrieved: str | None = None
    decay_rate: float = 0.023

    @classmethod
    def from_row(cls, row: dict[str, object]) -> "MemoryScore":
        return cls(
            memory_id=str(row.get("memory_id", "")),
            user_id=str(row.get("user_id", "unknown")),
            score_emotional=float(row.get("score_emotional", 0.5)),
            score_retrieval=float(row.get("score_retrieval", 0.0)),
            score_temporal=float(row.get("score_temporal", 1.0)),
            score_flagged=float(row.get("score_flagged", 0.0)),
            score_volume=float(row.get("score_volume", 0.3)),
            hms_score=float(row.get("hms_score", 0.5)),
            last_computed=str(row.get("last_computed", "")),
            last_retrieved=str(row["last_retrieved"]) if row.get("last_retrieved") is not None else None,
            decay_rate=float(row.get("decay_rate", 0.023)),
        )
