from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DriftLogEntry:
    run_date: str
    dimensions_before: dict[str, float]
    dimensions_after: dict[str, float]
    resonance_signals: dict[str, float]
    notes: str = ""

