"""Feature-flag aware module registry."""

from __future__ import annotations

from dataclasses import dataclass

from soul.config import Settings


@dataclass(slots=True)
class RegisteredFeature:
    key: str
    enabled: bool
    description: str


FeatureRegistry = dict[str, RegisteredFeature]


def build_feature_registry(settings: Settings) -> FeatureRegistry:
    return {
        "telegram": RegisteredFeature(
            key="telegram",
            enabled=settings.enable_telegram,
            description="Telegram polling and delivery surface.",
        ),
        "voice": RegisteredFeature(
            key="voice",
            enabled=settings.enable_voice,
            description="Voice recording, transcription, and synthesis surface.",
        ),
        "proactive": RegisteredFeature(
            key="proactive",
            enabled=settings.enable_proactive,
            description="Proactive candidate generation and delivery gating.",
        ),
        "reflection": RegisteredFeature(
            key="reflection",
            enabled=settings.enable_reflection,
            description="Monthly reflection generation and persistence.",
        ),
        "drift": RegisteredFeature(
            key="drift",
            enabled=settings.enable_drift,
            description="Slow personality evolution and drift reporting.",
        ),
        "background_jobs": RegisteredFeature(
            key="background_jobs",
            enabled=settings.enable_background_jobs,
            description="Maintenance runner and scheduled upkeep tasks.",
        ),
    }
