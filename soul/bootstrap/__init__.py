"""Bootstrap helpers for startup, config, and validation."""

from soul.bootstrap.errors import (
    ConfigurationError,
    DatabaseUnavailableError,
    ExtractionValidationError,
    FeatureInitializationError,
    ModelProviderError,
    PersistenceError,
    SchemaInitializationError,
    StartupDependencyError,
    TurnExecutionError,
)
from soul.bootstrap.feature_registry import FeatureRegistry, RegisteredFeature, build_feature_registry
from soul.bootstrap.validator import StartupReport, validate_startup

__all__ = [
    "ConfigurationError",
    "DatabaseUnavailableError",
    "ExtractionValidationError",
    "FeatureInitializationError",
    "FeatureRegistry",
    "ModelProviderError",
    "PersistenceError",
    "RegisteredFeature",
    "SchemaInitializationError",
    "StartupDependencyError",
    "StartupReport",
    "TurnExecutionError",
    "build_feature_registry",
    "validate_startup",
]
