from __future__ import annotations

from datetime import datetime, timezone

import pytest

from soul.config import Settings
from soul.core.mood_engine import MoodEngine


@pytest.mark.live_llm
def test_mood_engine_analyze_uses_openai_mood_label(monkeypatch, live_llm_requested, request):
    if live_llm_requested:
        settings = request.getfixturevalue("live_llm_runtime_settings")
        engine = MoodEngine(settings)

        mood_snapshot = engine.analyze(
            "I feel overwhelmed by work and hate how heavy this week feels.",
            user_id="test-user-label",
            now=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
        )

        assert mood_snapshot.user_mood in settings.mood_valid_labels
        assert mood_snapshot.companion_state in MoodEngine.STATE_MAP.values()
        assert mood_snapshot.rationale.startswith("openai mood prompt")
        return

    settings = Settings(_env_file=None)
    engine = MoodEngine(settings)
    monkeypatch.setattr(
        MoodEngine,
        "_openai_mood",
        lambda self, text: ("venting", 0.91, "fixture mood classification"),
    )

    mood_snapshot = engine.analyze(
        "I hate this so much",
        user_id="test-user-label",
        now=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
    )

    assert mood_snapshot.user_mood == "venting"
    assert mood_snapshot.companion_state == "warm"
    assert mood_snapshot.confidence == pytest.approx(0.91, abs=0.01)
    assert mood_snapshot.rationale == "fixture mood classification"


@pytest.mark.live_llm
def test_mood_engine_retains_state_without_redis(monkeypatch, live_llm_requested, request):
    if live_llm_requested:
        settings = request.getfixturevalue("live_llm_runtime_settings")
        engine = MoodEngine(settings)
        now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)

        first = engine.analyze("I feel stressed and overloaded today.", user_id="test-user-state", now=now)
        second = engine.analyze("okay", user_id="test-user-state", now=now)

        assert first.companion_state in MoodEngine.STATE_MAP.values()
        assert second.companion_state in MoodEngine.STATE_MAP.values()
        assert engine.current_state("test-user-state") is not None
        return

    settings = Settings(_env_file=None)
    engine = MoodEngine(settings)
    now = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
    responses = iter(
        [
            ("venting", 0.91, "first fixture mood classification"),
            ("neutral", 0.52, "second fixture mood classification"),
        ]
    )

    monkeypatch.setattr(MoodEngine, "_openai_mood", lambda self, text: next(responses))

    first = engine.analyze("I hate this", user_id="test-user-state", now=now)
    second = engine.analyze("okay", user_id="test-user-state", now=now)

    assert first.companion_state == "warm"
    assert second.companion_state == "warm"
    assert second.user_mood == "neutral"


def test_openai_mood_raises_when_no_api_key(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        openai_api_key=None,
    )
    engine = MoodEngine(settings)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        engine.analyze("I had a rough day")


def test_mood_engine_falls_back_on_invalid_label(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    engine = MoodEngine(settings)

    def fake(self, text):  # noqa: ANN001, ARG001
        raise ValueError("unrecognised mood label 'angry'")

    monkeypatch.setattr(MoodEngine, "_openai_mood", fake)
    mood_snapshot = engine.analyze("I am angry", persist=False)
    assert mood_snapshot.user_mood == "neutral"
    assert mood_snapshot.companion_state == "neutral"
    assert mood_snapshot.confidence == 0.0


def test_mood_engine_maps_settings_label_not_in_state_map_to_neutral(tmp_path, monkeypatch):
    # Simulate the provider returning a label that is allowed by config but
    # doesn't have a mapping in STATE_MAP. The engine should degrade safely.
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        openai_api_key="dummy-key",
        mood_valid_labels=[
            "venting",
            "stressed",
            "celebrating",
            "curious",
            "reflective",
            "overwhelmed",
            "neutral",
            "angry",
        ],
    )
    engine = MoodEngine(settings)

    class _FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class _FakeChoice:
        def __init__(self, content: str) -> None:
            self.message = _FakeMessage(content)

    class _FakeResponse:
        def __init__(self, content: str) -> None:
            self.choices = [_FakeChoice(content)]

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
            self.chat = self
            self.completions = self

        def create(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            return _FakeResponse('{"mood":"angry","confidence":0.7}')

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    mood_snapshot = engine.analyze("I am angry", persist=False)
    assert mood_snapshot.user_mood == "neutral"
    assert mood_snapshot.companion_state == "neutral"
    assert mood_snapshot.confidence == pytest.approx(0.7, abs=0.01)
    assert mood_snapshot.rationale.startswith("openai mood prompt")


def test_mood_engine_falls_back_on_invalid_openai_payload(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        openai_api_key="dummy-key",
    )
    engine = MoodEngine(settings)

    class _FakeResponse:
        def __init__(self) -> None:
            self.choices = [type("C", (), {"message": type("M", (), {"content": "not json"})()})]

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
            self.chat = self
            self.completions = self

        def create(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            return _FakeResponse()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    mood_snapshot = engine.analyze("I hate this", persist=False)
    assert mood_snapshot.user_mood == "neutral"
    assert mood_snapshot.companion_state == "neutral"
    assert mood_snapshot.confidence == 0.0


def test_mood_engine_falls_back_on_openai_failure(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        openai_api_key="dummy-key",
    )
    engine = MoodEngine(settings)

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002, ANN003
            self.chat = self
            self.completions = self

        def create(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("timeout")

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    mood_snapshot = engine.analyze("I hate this", persist=False)
    assert mood_snapshot.user_mood == "neutral"
    assert mood_snapshot.companion_state == "neutral"
    assert mood_snapshot.confidence == 0.0
