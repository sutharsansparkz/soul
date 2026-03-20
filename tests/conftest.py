from __future__ import annotations

import pytest

from soul.config import get_settings


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
