from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from soul.config import Settings
from soul.core.llm_client import LLMClient
from soul.core.mood_engine import MoodEngine
from soul.core.soul_loader import Soul


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "persona_conversations.json"


def test_persona_fixture_has_20_plus_cases():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(payload) >= 20


def test_persona_regression_fixtures_are_stable_and_deterministic(tmp_path, monkeypatch):
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    settings = Settings(
        openai_api_key=None,
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        redis_url="redis://localhost:6399/0",
    )
    soul = Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )
    engine = MoodEngine(settings)
    client = LLMClient(settings, soul)
    fixed_now = datetime(2026, 3, 19, 14, 30, tzinfo=timezone.utc)

    def fake_reply(
        self,
        *,
        system_prompt,
        messages,
        mood,
        stream_handler=None,
        reply_phrase="",
    ):  # noqa: ANN001, ARG001
        if stream_handler is not None:
            stream_handler(reply_phrase)
        return SimpleNamespace(
            text=reply_phrase,
            provider="mock-openai",
            model="mock",
            fallback_used=False,
            error=None,
        )

    for case in payload:
        expected_mood = case["expected_user_mood"]
        expected_reply_phrase = case["expected_reply_phrase"]

        def mock_openai_mood(self, text, _mood=expected_mood):  # noqa: ANN001, ARG001
            return (_mood, 0.85, "test-fixture")

        def mock_reply(
            self,
            *,
            system_prompt,
            messages,
            mood,
            stream_handler=None,
            _reply_phrase=expected_reply_phrase,
        ):  # noqa: ANN001, ARG001
            return fake_reply(
                self,
                system_prompt=system_prompt,
                messages=messages,
                mood=mood,
                stream_handler=stream_handler,
                reply_phrase=_reply_phrase,
            )

        monkeypatch.setattr(MoodEngine, "_openai_mood", mock_openai_mood)
        monkeypatch.setattr(LLMClient, "reply", mock_reply)
        mood = engine.analyze(case["user_input"], user_id="persona-fixture", now=fixed_now)
        result = client.reply(
            system_prompt="You are Ara.",
            messages=[{"role": "user", "content": case["user_input"]}],
            mood=mood,
        )
        assert mood.user_mood == case["expected_user_mood"], case["id"]
        assert mood.companion_state == case["expected_companion_state"], case["id"]
        assert case["expected_reply_phrase"] in result.text.casefold(), case["id"]
        assert result.provider == "mock-openai", case["id"]
