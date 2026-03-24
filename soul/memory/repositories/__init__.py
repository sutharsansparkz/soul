"""SQLite-backed repositories for SOUL domain state."""

from soul.memory.repositories.app_settings import AppSettingsRepository
from soul.memory.repositories.episodic import EpisodicMemoryRepository
from soul.memory.repositories.maintenance import MaintenanceRunRepository
from soul.memory.repositories.messages import MessagesRepository
from soul.memory.repositories.milestones import MilestonesRepository
from soul.memory.repositories.mood import MoodSnapshotsRepository
from soul.memory.repositories.personality import PersonalityStateRepository
from soul.memory.repositories.proactive import ProactiveCandidateRepository
from soul.memory.repositories.reflections import ReflectionArtifact, ReflectionArtifactsRepository
from soul.memory.repositories.shared_language import SharedLanguageRepository
from soul.memory.repositories.user_facts import UserFactsRepository

__all__ = [
    "AppSettingsRepository",
    "EpisodicMemoryRepository",
    "MaintenanceRunRepository",
    "MessagesRepository",
    "MilestonesRepository",
    "MoodSnapshotsRepository",
    "PersonalityStateRepository",
    "ProactiveCandidateRepository",
    "ReflectionArtifact",
    "ReflectionArtifactsRepository",
    "SharedLanguageRepository",
    "UserFactsRepository",
]
