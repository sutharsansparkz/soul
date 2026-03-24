"""Startup validation for the strict SQLite-only runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from soul.bootstrap.errors import (
    ConfigurationError,
    DatabaseUnavailableError,
    FeatureInitializationError,
    ModelProviderError,
    SchemaInitializationError,
    StartupDependencyError,
)
from soul.bootstrap.feature_registry import FeatureRegistry, build_feature_registry
from soul.config import Settings
from soul.persistence.db import connect, ensure_sqlite_url
from soul.persistence.sqlite_setup import ensure_schema, find_obsolete_legacy_files


@dataclass(slots=True)
class StartupReport:
    diagnostics: list[str] = field(default_factory=list)
    feature_registry: FeatureRegistry = field(default_factory=dict)

    def add(self, message: str) -> None:
        self.diagnostics.append(message)


def validate_startup(settings: Settings, *, ensure_schema_ready: bool = True) -> StartupReport:
    report = StartupReport()
    feature_registry = build_feature_registry(settings)
    report.feature_registry = feature_registry

    report.add("[BOOT] Loading config...")
    _validate_config(settings)
    report.add("[OK] Config valid")

    report.add("[BOOT] Opening SQLite database...")
    try:
        with connect(settings.database_url) as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception as exc:  # pragma: no cover - exercised via tests with monkeypatching
        raise DatabaseUnavailableError(str(exc)) from exc
    report.add("[OK] SQLite connected")

    if ensure_schema_ready:
        report.add("[BOOT] Ensuring schema...")
        try:
            ensure_schema(settings.database_url)
        except Exception as exc:  # pragma: no cover - exercised via tests with monkeypatching
            raise SchemaInitializationError(str(exc)) from exc
        report.add("[OK] Schema ready")

    obsolete_files = find_obsolete_legacy_files(settings)
    if obsolete_files:
        raise StartupDependencyError(
            "Obsolete legacy state files are present in SOUL_DATA_DIR and are no longer supported: "
            + ", ".join(path.name for path in obsolete_files)
        )

    report.add("[BOOT] Checking LLM provider...")
    _validate_model_provider(settings)
    report.add("[OK] Provider ready")

    for feature in feature_registry.values():
        if not feature.enabled:
            continue
        report.add(f"[BOOT] Checking enabled feature: {feature.key}...")
        _validate_feature(settings, feature.key)
        report.add(f"[OK] {feature.description.split('.')[0]} ready")

    return report


def _validate_config(settings: Settings) -> None:
    ensure_sqlite_url(settings.database_url)
    if not settings.soul_file.exists():
        settings.soul_file.parent.mkdir(parents=True, exist_ok=True)
        settings.soul_file.write_text(settings.default_soul_yaml, encoding="utf-8")
        try:
            settings.soul_file.chmod(0o600)
        except OSError:
            pass

    if not settings.soul_data_dir.exists():
        settings.soul_data_dir.mkdir(parents=True, exist_ok=True)

    for path in (settings.sqlite_path.parent, settings.session_log_dir, settings.session_archive_dir, settings.exports_dir):
        path.mkdir(parents=True, exist_ok=True)

    try:
        ZoneInfo(settings.timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(f"Invalid SOUL_TIMEZONE: {settings.timezone_name}") from exc


def _validate_model_provider(settings: Settings) -> None:
    if not settings.openai_api_key:
        raise ModelProviderError("OPENAI_API_KEY is required.")
    if not settings.llm_model.strip():
        raise ModelProviderError("LLM_MODEL is required.")
    if not settings.mood_openai_model.strip():
        raise ModelProviderError("MOOD_OPENAI_MODEL is required.")


def _validate_feature(settings: Settings, feature_key: str) -> None:
    if feature_key == "telegram":
        if not settings.telegram_bot_token:
            raise FeatureInitializationError("ENABLE_TELEGRAM is true but TELEGRAM_BOT_TOKEN is missing.")
        if not settings.telegram_chat_id:
            raise FeatureInitializationError("ENABLE_TELEGRAM is true but TELEGRAM_CHAT_ID is missing.")
        try:
            int(str(settings.telegram_chat_id))
        except ValueError as exc:
            raise FeatureInitializationError("TELEGRAM_CHAT_ID must be an integer.") from exc
        return

    if feature_key == "voice":
        if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
            raise FeatureInitializationError(
                "ENABLE_VOICE is true but ElevenLabs credentials are incomplete."
            )
        try:
            __import__("whisper")
        except Exception as exc:
            raise FeatureInitializationError("ENABLE_VOICE is true but `whisper` is unavailable.") from exc
        try:
            __import__("sounddevice")
        except Exception as exc:
            raise FeatureInitializationError("ENABLE_VOICE is true but `sounddevice` is unavailable.") from exc
        return

    if feature_key == "background_jobs":
        if settings.maintenance_retention_days < 1:
            raise FeatureInitializationError("MAINTENANCE_RETENTION_DAYS must be >= 1.")
        return

    if feature_key in {"proactive", "reflection", "drift"}:
        # These features are local services backed by SQLite and the LLM provider.
        return

    raise FeatureInitializationError(f"Unknown feature flag: {feature_key}")
