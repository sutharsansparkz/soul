from __future__ import annotations

import os
import shutil
import threading
import time

import pytest

from soul import db
from soul.config import Settings, get_settings
from soul.core.llm_client import LLMClient
from soul.core.mood_engine import MoodEngine


def _live_llm_enabled() -> bool:
    return os.environ.get("SOUL_LIVE_LLM_TESTS", "").strip().casefold() in {"1", "true", "yes", "on"}


_LIVE_LLM_LOCK = threading.Lock()
_LIVE_LLM_LAST_CALL_AT = 0.0


def _wait_for_live_llm_slot(min_interval_seconds: float = 7.5) -> None:
    global _LIVE_LLM_LAST_CALL_AT
    with _LIVE_LLM_LOCK:
        now = time.monotonic()
        remaining = (_LIVE_LLM_LAST_CALL_AT + min_interval_seconds) - now
        if remaining > 0:
            time.sleep(remaining)
        _LIVE_LLM_LAST_CALL_AT = time.monotonic()


@pytest.fixture(scope="session")
def live_llm_requested() -> bool:
    return _live_llm_enabled()


@pytest.fixture(scope="session")
def live_llm_provider_settings() -> Settings:
    if not _live_llm_enabled():
        pytest.skip("Set SOUL_LIVE_LLM_TESTS=1 to run live LLM integration tests.")

    settings = get_settings()
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY is required for live LLM integration tests.")
    return settings


@pytest.fixture
def live_llm_runtime_settings(tmp_path, live_llm_provider_settings: Settings) -> Settings:
    soul_data_dir = tmp_path / "soul_data"
    soul_data_dir.mkdir(parents=True, exist_ok=True)

    source_soul = live_llm_provider_settings.soul_file
    target_soul = soul_data_dir / "soul.yaml"
    if source_soul.exists():
        shutil.copy2(source_soul, target_soul)
    else:
        target_soul.write_text(
            'identity:\n  name: "Ara"\n  voice: "warm"\n  energy: "steady"\ncharacter: {}\nethics: {}\nworldview: {}\n',
            encoding="utf-8",
        )

    settings = Settings(
        _env_file=None,
        openai_api_key=live_llm_provider_settings.openai_api_key.get_secret_value(),
        openai_base_url=live_llm_provider_settings.openai_base_url,
        llm_model=live_llm_provider_settings.llm_model,
        llm_max_tokens=min(160, live_llm_provider_settings.llm_max_tokens),
        llm_temperature=0.0,
        mood_openai_model=live_llm_provider_settings.mood_openai_model,
        mood_openai_max_tokens=live_llm_provider_settings.mood_openai_max_tokens,
        mood_openai_temperature=0.0,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(soul_data_dir),
        user_id="live-llm-test-user",
        timezone_name="UTC",
    )
    db.init_db(settings.database_url)
    return settings


@pytest.fixture(autouse=True)
def isolate_env_file_for_non_live_tests(request):
    original_env_file = Settings.model_config.get("env_file")
    if request.node.get_closest_marker("live_llm") is not None:
        yield
        return

    Settings.model_config["env_file"] = None
    get_settings.cache_clear()
    try:
        yield
    finally:
        Settings.model_config["env_file"] = original_env_file
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def throttle_live_llm_tests(request, monkeypatch):
    if request.node.get_closest_marker("live_llm") is None:
        yield
        return

    original_reply = LLMClient.reply
    original_complete_text = LLMClient.complete_text
    original_openai_mood = MoodEngine._openai_mood

    from openai import APIConnectionError, RateLimitError

    def _maybe_skip_live_llm_error(exc: Exception) -> None:
        if isinstance(exc, (RateLimitError, APIConnectionError)):
            pytest.skip(f"Live LLM unavailable during test run: {exc}")

    def throttled_reply(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        _wait_for_live_llm_slot()
        try:
            return original_reply(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            _maybe_skip_live_llm_error(exc)
            raise

    def throttled_complete_text(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        _wait_for_live_llm_slot()
        try:
            return original_complete_text(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            _maybe_skip_live_llm_error(exc)
            raise

    def throttled_openai_mood(self, text):  # noqa: ANN001
        _wait_for_live_llm_slot()
        try:
            return original_openai_mood(self, text)
        except Exception as exc:  # noqa: BLE001
            _maybe_skip_live_llm_error(exc)
            raise

    monkeypatch.setattr(LLMClient, "reply", throttled_reply)
    monkeypatch.setattr(LLMClient, "complete_text", throttled_complete_text)
    monkeypatch.setattr(MoodEngine, "_openai_mood", throttled_openai_mood)
    yield


@pytest.fixture(autouse=True)
def reset_global_caches():
    get_settings.cache_clear()
    try:
        from soul.memory.episodic import _INITIALIZED_DATABASES

        _INITIALIZED_DATABASES.clear()
    except ImportError:
        pass
    yield
    get_settings.cache_clear()
    try:
        from soul.memory.episodic import _INITIALIZED_DATABASES

        _INITIALIZED_DATABASES.clear()
    except ImportError:
        pass
