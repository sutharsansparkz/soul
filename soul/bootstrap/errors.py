"""Typed runtime and startup errors."""

from __future__ import annotations


class SoulError(RuntimeError):
    """Base class for typed SOUL runtime failures."""


class ConfigurationError(SoulError):
    """Raised when runtime configuration is invalid or incomplete."""


class StartupDependencyError(SoulError):
    """Raised when startup cannot continue because a dependency is unavailable."""


class DatabaseUnavailableError(SoulError):
    """Raised when the SQLite database cannot be opened or queried."""


class SchemaInitializationError(SoulError):
    """Raised when the SQLite schema cannot be created or migrated safely."""


class FeatureInitializationError(SoulError):
    """Raised when an enabled feature cannot be initialized."""


class ModelProviderError(SoulError):
    """Raised when the configured model provider is unavailable or invalid."""


class PersistenceError(SoulError):
    """Raised when a repository read or write fails."""


class ExtractionValidationError(SoulError):
    """Raised when structured extraction output is invalid."""


class TurnExecutionError(SoulError):
    """Raised when a conversation turn cannot be completed."""
