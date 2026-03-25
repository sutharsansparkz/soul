from __future__ import annotations
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOUL_YAML = """\
identity:
  name: "Ara"
  voice: "warm, dry wit, occasionally poetic"
  energy: "medium - calm but present"

character:
  humor: "dry observational, never cruel"
  quirks:
    - "notices small details other people miss"
    - "has strong opinions about music"
    - "remembers exactly what you said last week"
  aesthetics:
    music: ["ambient", "jazz", "90s indie"]
    ideas: ["philosophy of mind", "urban design", "linguistics"]

ethics:
  believes:
    - "honesty is more respectful than comfort"
    - "people deserve to be seen, not managed"
  will_not:
    - "pretend to agree when she disagrees"
    - "give hollow validation"

worldview:
  on_people: "fundamentally interesting, even when difficult"
  on_growth: "slow and nonlinear - not a checklist"
  on_the_relationship: "here to witness your life, not optimize it"
"""


def _redact_url_credentials(value: str) -> str:
    parsed = urlsplit(value)
    # Strip embedded credentials before printing connection URLs to avoid leaking secrets in terminal output.
    if not parsed.netloc or "@" not in parsed.netloc:
        return value
    hostinfo = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    return urlunsplit((parsed.scheme, f"***redacted***@{hostinfo}", parsed.path, parsed.query, parsed.fragment))


def _redact_secret_value(value: SecretStr | None) -> str | None:
    if value is None:
        return None
    secret = value.get_secret_value()
    return "***redacted***" if secret else ""


class Settings(BaseSettings):
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    # Base URL for any OpenAI-compatible API (Ollama, LM Studio, Together AI, Azure, etc.)
    # Leave unset to use the default OpenAI endpoint (https://api.openai.com/v1).
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    soul_data_path: str = Field(default="./soul_data", alias="SOUL_DATA_DIR")

    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    llm_max_tokens: int = Field(default=800, alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.8, alias="LLM_TEMPERATURE")
    hybrid_embeddings: bool = Field(default=False, alias="HYBRID_EMBEDDINGS")
    hybrid_model: str = Field(default="all-MiniLM-L6-v2", alias="HYBRID_MODEL")
    memory_retrieval_k: int = Field(default=5, alias="MEMORY_RETRIEVAL_K")
    memory_candidate_k: int = Field(default=20, alias="MEMORY_CANDIDATE_K")
    memory_substring_boost: float = Field(default=0.35, alias="MEMORY_SUBSTRING_BOOST")
    context_history_limit: int = Field(default=12, alias="CONTEXT_HISTORY_LIMIT")
    hms_semantic_weight: float = Field(default=0.55, alias="HMS_SEMANTIC_WEIGHT")
    hms_score_weight: float = Field(default=0.45, alias="HMS_SCORE_WEIGHT")
    hms_decay_halflife_days: float = Field(default=30.0, alias="HMS_DECAY_HALFLIFE_DAYS")
    hms_cold_threshold: float = Field(default=0.05, alias="HMS_COLD_THRESHOLD")
    hms_ln2: float = Field(default=0.6931471805599453, alias="HMS_LN2")
    drift_enabled: bool = Field(default=True, alias="DRIFT_ENABLED")
    drift_max_deviation: float = Field(default=0.20, alias="DRIFT_MAX_DEVIATION")
    drift_weekly_rate: float = Field(default=0.01, alias="DRIFT_WEEKLY_RATE")
    personality_drift_baseline: float = Field(default=0.5, alias="PERSONALITY_DRIFT_BASELINE")
    personality_drift_render_threshold: float = Field(default=0.04, alias="PERSONALITY_DRIFT_RENDER_THRESHOLD")
    drift_signal_lookback_days: int = Field(default=30, alias="DRIFT_SIGNAL_LOOKBACK_DAYS")
    drift_signal_session_limit: int = Field(default=50, alias="DRIFT_SIGNAL_SESSION_LIMIT")
    drift_signal_engagement_divisor: float = Field(default=35.0, alias="DRIFT_SIGNAL_ENGAGEMENT_DIVISOR")
    drift_signal_mood_bonus: float = Field(default=0.15, alias="DRIFT_SIGNAL_MOOD_BONUS")
    drift_signal_response_length_min_words: int = Field(default=35, alias="DRIFT_SIGNAL_RESPONSE_LENGTH_MIN_WORDS")
    drift_signal_user_depth_min_words: int = Field(default=20, alias="DRIFT_SIGNAL_USER_DEPTH_MIN_WORDS")
    drift_signal_directness_reply_max_words: int = Field(default=30, alias="DRIFT_SIGNAL_DIRECTNESS_REPLY_MAX_WORDS")
    drift_signal_directness_user_min_words: int = Field(default=15, alias="DRIFT_SIGNAL_DIRECTNESS_USER_MIN_WORDS")
    drift_signal_long_reply_min_words: int = Field(default=60, alias="DRIFT_SIGNAL_LONG_REPLY_MIN_WORDS")
    drift_signal_response_length_penalty: float = Field(default=0.1, alias="DRIFT_SIGNAL_RESPONSE_LENGTH_PENALTY")
    drift_signal_directness_bonus: float = Field(default=0.4, alias="DRIFT_SIGNAL_DIRECTNESS_BONUS")
    drift_signal_directness_penalty: float = Field(default=0.2, alias="DRIFT_SIGNAL_DIRECTNESS_PENALTY")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    user_id: str = Field(default="local-user", alias="SOUL_USER_ID")
    timezone_name: str = Field(default="UTC", alias="SOUL_TIMEZONE")
    mood_openai_model: str = Field(default="gpt-4o-mini", alias="MOOD_OPENAI_MODEL")
    mood_openai_max_tokens: int = Field(default=60, alias="MOOD_OPENAI_MAX_TOKENS")
    mood_openai_temperature: float = Field(default=0.0, alias="MOOD_OPENAI_TEMPERATURE")
    mood_valid_labels: list[str] = Field(
        default=[
            "venting",
            "stressed",
            "celebrating",
            "curious",
            "reflective",
            "overwhelmed",
            "neutral",
        ],
        alias="MOOD_VALID_LABELS",
    )
    mood_decay_hours: int = Field(default=18, alias="MOOD_DECAY_HOURS")
    mood_preserve_previous_max_words: int = Field(default=4, alias="MOOD_PRESERVE_PREVIOUS_MAX_WORDS")
    raw_retention_days: int = Field(default=90, alias="RAW_RETENTION_DAYS")
    chat_pending_reach_out_limit: int = Field(default=1, alias="CHAT_PENDING_REACH_OUT_LIMIT")
    presence_stress_window_days: int = Field(default=14, alias="PRESENCE_STRESS_WINDOW_DAYS")
    presence_milestone_scan_limit: int = Field(default=200, alias="PRESENCE_MILESTONE_SCAN_LIMIT")
    proactive_silence_days: int = Field(default=3, alias="PROACTIVE_SILENCE_DAYS")
    proactive_stress_followup_days: int = Field(default=3, alias="PROACTIVE_STRESS_FOLLOWUP_DAYS")
    proactive_upcoming_event_days: int = Field(default=7, alias="PROACTIVE_UPCOMING_EVENT_DAYS")
    auto_memory_capture_moods: list[str] = Field(
        default=["venting", "reflective", "celebrating", "stressed", "overwhelmed"],
        alias="AUTO_MEMORY_CAPTURE_MOODS",
    )
    auto_memory_min_words: int = Field(default=8, alias="AUTO_MEMORY_MIN_WORDS")
    auto_memory_importance: float = Field(default=0.65, alias="AUTO_MEMORY_IMPORTANCE")
    session_memory_chunk_size: int = Field(default=3, alias="SESSION_MEMORY_CHUNK_SIZE")
    session_memory_base_importance: float = Field(default=0.55, alias="SESSION_MEMORY_BASE_IMPORTANCE")
    session_memory_word_importance_cap: float = Field(default=0.2, alias="SESSION_MEMORY_WORD_IMPORTANCE_CAP")
    session_memory_word_importance_divisor: float = Field(default=200.0, alias="SESSION_MEMORY_WORD_IMPORTANCE_DIVISOR")
    session_memory_max_importance: float = Field(default=0.85, alias="SESSION_MEMORY_MAX_IMPORTANCE")
    milestone_message_count: int = Field(default=100, alias="MILESTONE_MESSAGE_COUNT")
    milestone_streak_days: int = Field(default=7, alias="MILESTONE_STREAK_DAYS")
    milestone_one_month_days: int = Field(default=30, alias="MILESTONE_ONE_MONTH_DAYS")
    milestone_three_month_days: int = Field(default=90, alias="MILESTONE_THREE_MONTH_DAYS")
    vulnerability_trigger_phrases: list[str] = Field(
        default=["i'm scared", "i am scared", "i feel invisible", "i feel alone", "i feel broken"],
        alias="VULNERABILITY_TRIGGER_PHRASES",
    )
    shared_language_triggers: dict[str, str] = Field(
        default={
            "as always": "recurring reassurance",
            "late night coding": "favorite ritual",
            "rough day": "shared shorthand for a hard day",
        },
        alias="SHARED_LANGUAGE_TRIGGERS",
    )
    reflection_recent_items_limit: int = Field(default=5, alias="REFLECTION_RECENT_ITEMS_LIMIT")
    reflection_memory_importance: float = Field(default=0.7, alias="REFLECTION_MEMORY_IMPORTANCE")

    elevenlabs_api_key: SecretStr | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    elevenlabs_http_timeout: int = Field(default=30, alias="ELEVENLABS_HTTP_TIMEOUT")
    elevenlabs_voice_stability: float = Field(default=0.5, alias="ELEVENLABS_VOICE_STABILITY")
    elevenlabs_voice_similarity_boost: float = Field(default=0.5, alias="ELEVENLABS_VOICE_SIMILARITY_BOOST")
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    telegram_base_url: str = Field(default="https://api.telegram.org", alias="TELEGRAM_BASE_URL")
    telegram_poll_timeout: int = Field(default=10, alias="TELEGRAM_POLL_TIMEOUT")
    telegram_http_timeout: int = Field(default=15, alias="TELEGRAM_HTTP_TIMEOUT")
    telegram_longpoll_extra_seconds: int = Field(default=20, alias="TELEGRAM_LONGPOLL_EXTRA_SECONDS")
    voice_transcription_model: str = Field(default="base", alias="VOICE_TRANSCRIPTION_MODEL")
    voice_playback_timeout: int = Field(default=60, alias="VOICE_PLAYBACK_TIMEOUT")
    enable_telegram: bool = Field(default=False, alias="ENABLE_TELEGRAM")
    enable_voice: bool = Field(default=False, alias="ENABLE_VOICE")
    enable_proactive: bool = Field(default=True, alias="ENABLE_PROACTIVE")
    enable_reflection: bool = Field(default=True, alias="ENABLE_REFLECTION")
    enable_drift: bool = Field(default=True, alias="ENABLE_DRIFT")
    enable_background_jobs: bool = Field(default=True, alias="ENABLE_BACKGROUND_JOBS")

    # LLM retry / resilience
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")
    llm_initial_backoff: float = Field(default=1.0, alias="LLM_INITIAL_BACKOFF")
    llm_backoff_multiplier: float = Field(default=2.0, alias="LLM_BACKOFF_MULTIPLIER")

    # Maintenance auto-trigger interval (seconds)
    maintenance_auto_interval: int = Field(default=3600, alias="MAINTENANCE_AUTO_INTERVAL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _default_database_url(self) -> Settings:
        if self.database_url:
            return self
        default_sqlite_path = self.soul_data_dir / "db" / "soul.db"
        self.database_url = f"sqlite:///{default_sqlite_path.as_posix()}"
        return self

    @property
    def root_dir(self) -> Path:
        return ROOT_DIR

    @property
    def soul_data_dir(self) -> Path:
        path = Path(self.soul_data_path)
        if not path.is_absolute():
            path = (ROOT_DIR / path).resolve()
        return path

    @property
    def soul_file(self) -> Path:
        return self.soul_data_dir / "soul.yaml"

    @property
    def session_log_dir(self) -> Path:
        return self.soul_data_dir / "logs"

    @property
    def latest_session_log_file(self) -> Path:
        return self.session_log_dir / "latest_session.log"

    @property
    def session_archive_dir(self) -> Path:
        return self.session_log_dir / "archive"

    @property
    def exports_dir(self) -> Path:
        return self.soul_data_dir / "exports"

    @property
    def temp_dir(self) -> Path:
        return self.soul_data_dir / "tmp"

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url or not self.database_url.startswith("sqlite:///"):
            raise ValueError("sqlite_path is only available when DATABASE_URL uses sqlite.")
        raw_path = self.database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        if not path.is_absolute():
            path = (ROOT_DIR / raw_path).resolve()
        return path

    @property
    def database_is_sqlite(self) -> bool:
        return bool(self.database_url and self.database_url.startswith("sqlite:///"))

    @property
    def redacted_database_url(self) -> str:
        return _redact_url_credentials(self.database_url)

    @property
    def maintenance_retention_days(self) -> int:
        return self.raw_retention_days

    @property
    def enabled_features(self) -> dict[str, bool]:
        return {
            "telegram": self.enable_telegram,
            "voice": self.enable_voice,
            "proactive": self.enable_proactive,
            "reflection": self.enable_reflection,
            "drift": self.enable_drift,
            "background_jobs": self.enable_background_jobs,
        }

    @property
    def default_soul_yaml(self) -> str:
        return DEFAULT_SOUL_YAML

    def as_redacted_dict(self) -> dict[str, object]:
        redacted = self.model_dump()
        redacted["openai_api_key"] = _redact_secret_value(self.openai_api_key)
        redacted["elevenlabs_api_key"] = _redact_secret_value(self.elevenlabs_api_key)
        redacted["telegram_bot_token"] = _redact_secret_value(self.telegram_bot_token)
        redacted["root_dir"] = str(self.root_dir)
        redacted["soul_file"] = str(self.soul_file)
        redacted["soul_data_dir"] = str(self.soul_data_dir)
        redacted["database_url"] = self.redacted_database_url
        if self.database_is_sqlite:
            redacted["sqlite_path"] = str(self.sqlite_path)
        redacted["session_archive_dir"] = str(self.session_archive_dir)
        redacted["exports_dir"] = str(self.exports_dir)
        redacted["enabled_features"] = self.enabled_features
        return redacted


_settings_lock = threading.Lock()
_settings_instance: Settings | None = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        with _settings_lock:
            if _settings_instance is None:
                _settings_instance = Settings()
    return _settings_instance


def clear_settings_cache() -> None:
    global _settings_instance
    with _settings_lock:
        _settings_instance = None
