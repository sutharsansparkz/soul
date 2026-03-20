from __future__ import annotations

import pytest

from soul.config import Settings
from soul.core.mood_engine import MoodEngine


def test_mood_engine_uses_model_label_map_when_classifier_returns_result():
    settings = Settings(mood_model_enabled=True, redis_url="redis://localhost:6399/0")
    engine = MoodEngine(settings)
    fake_result = [[{"label": "anger", "score": 0.91}, {"label": "joy", "score": 0.05}]]

    engine.__dict__["classifier"] = lambda text, truncation=True: fake_result

    mood_tuple = engine._model_mood("I hate this so much")

    assert mood_tuple is not None
    assert mood_tuple[0] == "venting"
    assert mood_tuple[1] == pytest.approx(0.91, abs=0.01)
