"""Small in-process metrics helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TurnMetric:
    session_id: str
    latency_ms: float
    provider: str
    model: str
