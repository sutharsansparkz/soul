from __future__ import annotations

import os
import stat

from soul.cli import _ensure_runtime_files
from soul.config import Settings
from soul.core.soul_loader import load_soul
from soul import config


def test_ensure_runtime_files_creates_soul_yaml_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )

    assert not settings.soul_file.exists()

    _ensure_runtime_files(settings)

    assert settings.soul_file.exists()

    soul = load_soul(settings.soul_file)
    assert soul.name

    if os.name != "nt":
        assert stat.S_IMODE(settings.soul_file.stat().st_mode) == 0o600
