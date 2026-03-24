"""Typed LLM payload helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StructuredExtractionResult:
    facts: list[dict[str, object]] = field(default_factory=list)
    memories: list[dict[str, object]] = field(default_factory=list)
    shared_language: list[dict[str, object]] = field(default_factory=list)
    milestones: list[dict[str, object]] = field(default_factory=list)
