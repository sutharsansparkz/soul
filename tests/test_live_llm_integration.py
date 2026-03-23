from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from soul import db
import soul.cli as cli
from soul.config import Settings
from soul.core.llm_client import LLMClient
from soul.core.mood_engine import MoodEngine, MoodSnapshot
from soul.core.soul_loader import load_soul
from soul.tasks.consolidate import _extract_structured_insights


pytestmark = pytest.mark.live_llm


def test_live_llm_client_reply_streams_non_empty_text(live_llm_runtime_settings: Settings):
    soul = load_soul(live_llm_runtime_settings.soul_file)
    client = LLMClient(live_llm_runtime_settings, soul)
    streamed: list[str] = []

    result = client.reply(
        system_prompt="You are Ara. Reply with exactly one short sentence containing LIVE_OK.",
        messages=[{"role": "user", "content": "Reply with LIVE_OK exactly once."}],
        mood=MoodSnapshot(user_mood="neutral", companion_state="neutral", confidence=1.0, rationale="live-test"),
        stream_handler=streamed.append,
    )

    assert result.provider == "openai"
    assert result.text
    assert "LIVE_OK" in result.text
    assert "".join(streamed).strip() == result.text


def test_live_mood_engine_returns_supported_label(live_llm_runtime_settings: Settings):
    engine = MoodEngine(live_llm_runtime_settings)

    snapshot = engine.analyze(
        "I feel overwhelmed by work and need to slow down tonight.",
        user_id="live-mood-user",
        now=datetime(2026, 3, 23, 12, 0, tzinfo=timezone.utc),
    )

    assert snapshot.user_mood in live_llm_runtime_settings.mood_valid_labels
    assert snapshot.companion_state in MoodEngine.STATE_MAP.values()
    assert snapshot.rationale.startswith("openai mood prompt")


def test_live_chat_cli_turn_uses_real_llm_client(live_llm_runtime_settings: Settings, monkeypatch):
    soul = load_soul(live_llm_runtime_settings.soul_file)
    prompts = iter(["Reply with LIVE_CHAT_OK in one short sentence.", "/quit"])

    monkeypatch.setattr(cli, "_bootstrap", lambda: (live_llm_runtime_settings, soul))
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *args, **kwargs: next(prompts)))

    result = CliRunner().invoke(cli.app, ["chat"])

    assert result.exit_code == 0
    assert "LIVE_CHAT_OK" in result.stdout

    session_id = db.get_last_completed_session_id(live_llm_runtime_settings.database_url)
    rows = db.get_session_messages(live_llm_runtime_settings.database_url, session_id)
    assert any(row["role"] == "assistant" and "LIVE_CHAT_OK" in str(row["content"]) for row in rows)


def test_live_consolidation_extracts_structured_insights(live_llm_runtime_settings: Settings):
    insights = _extract_structured_insights(
        [
            "I am trying to launch the beta without burning out.",
            "Priya is my best friend and late night coding helps me calm down.",
        ],
        live_llm_runtime_settings,
    )

    assert insights is not None
    payload = {
        "summary": insights.summary,
        "current_mood_trend": insights.current_mood_trend,
        "active_goals": insights.active_goals,
        "active_fears": insights.active_fears,
        "values_observed": insights.values_observed,
        "relationships": insights.relationships,
        "shared_phrases": insights.shared_phrases,
        "big_moments": insights.big_moments,
    }
    assert json.dumps(payload)
    assert any(
        [
            bool(insights.summary),
            bool(insights.active_goals),
            bool(insights.active_fears),
            bool(insights.relationships),
            bool(insights.shared_phrases),
        ]
    )
