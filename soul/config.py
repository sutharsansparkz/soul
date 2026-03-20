from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent


def _redact_url_credentials(value: str) -> str:
    parsed = urlsplit(value)
    # Strip embedded credentials before printing connection URLs to avoid leaking secrets in terminal output.
    if not parsed.netloc or "@" not in parsed.netloc:
        return value
    hostinfo = parsed.netloc.rsplit("@", maxsplit=1)[-1]
    return urlunsplit((parsed.scheme, f"***redacted***@{hostinfo}", parsed.path, parsed.query, parsed.fragment))


class Settings(BaseSettings):
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")

    database_url: str = Field(default="sqlite:///./soul_data/db/soul.db", alias="DATABASE_URL")
    soul_data_path: str = Field(default="./soul_data", alias="SOUL_DATA_DIR")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

    llm_model: str = Field(default="claude-sonnet-4-6", alias="LLM_MODEL")
    llm_max_tokens: int = Field(default=800, alias="LLM_MAX_TOKENS")
    fallback_llm_model: str = Field(default="gpt-4o", alias="FALLBACK_LLM_MODEL")
    hybrid_embeddings: bool = Field(default=False, alias="HYBRID_EMBEDDINGS")
    hybrid_model: str = Field(default="all-MiniLM-L6-v2", alias="HYBRID_MODEL")
    memory_retrieval_k: int = Field(default=5, alias="MEMORY_RETRIEVAL_K")
    memory_candidate_k: int = Field(default=20, alias="MEMORY_CANDIDATE_K")
    hms_semantic_weight: float = Field(default=0.55, alias="HMS_SEMANTIC_WEIGHT")
    hms_score_weight: float = Field(default=0.45, alias="HMS_SCORE_WEIGHT")
    hms_decay_halflife_days: float = Field(default=30.0, alias="HMS_DECAY_HALFLIFE_DAYS")
    hms_cold_threshold: float = Field(default=0.05, alias="HMS_COLD_THRESHOLD")
    drift_enabled: bool = Field(default=True, alias="DRIFT_ENABLED")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    user_id: str = Field(default="local-user", alias="SOUL_USER_ID")
    timezone_name: str = Field(default="Asia/Calcutta", alias="SOUL_TIMEZONE")
    mood_model_name: str = Field(
        default="cardiffnlp/twitter-roberta-base-emotion",
        alias="MOOD_MODEL_NAME",
    )
    mood_model_enabled: bool = Field(default=False, alias="MOOD_MODEL_ENABLED")
    mood_decay_hours: int = Field(default=18, alias="MOOD_DECAY_HOURS")
    raw_retention_days: int = Field(default=90, alias="RAW_RETENTION_DAYS")
    redis_key_prefix: str = Field(default="soul", alias="REDIS_KEY_PREFIX")

    elevenlabs_api_key: SecretStr | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

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
    def personality_file(self) -> Path:
        return self.soul_data_dir / "personality.json"

    @property
    def user_story_file(self) -> Path:
        return self.soul_data_dir / "user_story.json"

    @property
    def drift_log_file(self) -> Path:
        return self.soul_data_dir / "drift_log.json"

    @property
    def shared_language_file(self) -> Path:
        return self.soul_data_dir / "shared_language.json"

    @property
    def reach_out_candidates_file(self) -> Path:
        return self.soul_data_dir / "reach_out_candidates.json"

    @property
    def reflections_file(self) -> Path:
        return self.soul_data_dir / "reflections.json"

    @property
    def milestones_file(self) -> Path:
        return self.soul_data_dir / "milestones.json"

    @property
    def episodic_memory_file(self) -> Path:
        return self.soul_data_dir / "episodic_memory.jsonl"

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
    def consolidation_ledger_file(self) -> Path:
        return self.soul_data_dir / "consolidation_ledger.json"

    @property
    def proactive_delivery_log_file(self) -> Path:
        return self.soul_data_dir / "proactive_delivery_log.json"

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("sqlite_path is only available when DATABASE_URL uses sqlite.")
        raw_path = self.database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        if not path.is_absolute():
            path = (ROOT_DIR / raw_path).resolve()
        return path

    @property
    def database_is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite:///")

    @property
    def redacted_database_url(self) -> str:
        return _redact_url_credentials(self.database_url)

    @property
    def redacted_redis_url(self) -> str:
        return _redact_url_credentials(self.redis_url)

    def as_redacted_dict(self) -> dict[str, object]:
        redacted = self.model_dump()
        for key in ("anthropic_api_key", "openai_api_key", "elevenlabs_api_key", "telegram_bot_token"):
            if redacted.get(key):
                redacted[key] = "***redacted***"
        redacted["root_dir"] = str(self.root_dir)
        redacted["soul_file"] = str(self.soul_file)
        redacted["personality_file"] = str(self.personality_file)
        redacted["user_story_file"] = str(self.user_story_file)
        redacted["soul_data_dir"] = str(self.soul_data_dir)
        redacted["database_url"] = self.redacted_database_url
        redacted["redis_url"] = self.redacted_redis_url
        if self.database_is_sqlite:
            redacted["sqlite_path"] = str(self.sqlite_path)
        redacted["session_archive_dir"] = str(self.session_archive_dir)
        return redacted


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
