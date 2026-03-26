"""Compatibility wrapper for the SQLite-only episodic repository."""

from soul.memory.repositories.episodic import EpisodicMemoryRepository
from soul.persistence.sqlite_setup import _INITIALIZED_DATABASES

__all__ = ["EpisodicMemoryRepository", "_INITIALIZED_DATABASES"]
