from __future__ import annotations

from types import SimpleNamespace

from soul.config import Settings
from soul.core.llm_client import LLMClient
from soul.core.mood_engine import MoodSnapshot
from soul.core.soul_loader import Soul


def _soul() -> Soul:
    return Soul(
        raw={"identity": {"name": "Ara", "voice": "warm", "energy": "steady"}, "character": {}, "ethics": {}, "worldview": {}},
        name="Ara",
        voice="warm",
        energy="steady",
    )


def test_llm_client_reply_uses_configured_max_tokens(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
        llm_max_tokens=123,
        llm_temperature=0.25,
    )
    client = LLMClient(settings, _soul())
    captured: dict[str, object] = {}

    def create(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return iter(
            [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))]
                )
            ]
        )

    client._openai = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    result = client.reply(
        system_prompt="You are Ara.",
        messages=[{"role": "user", "content": "Hi"}],
        mood=MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=1.0, rationale="test"),
    )

    assert captured["max_tokens"] == 123
    assert captured["temperature"] == 0.25
    assert result.text == "hello"
