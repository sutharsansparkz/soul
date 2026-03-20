from __future__ import annotations

import os
import stat

from soul.cli import _ensure_runtime_files
from soul.config import Settings


def test_runtime_files_created_with_restrictive_permissions(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    _ensure_runtime_files(settings)

    if os.name == "nt":
        return

    soul_data_stat = settings.soul_data_dir.stat()
    assert stat.S_IMODE(soul_data_stat.st_mode) == 0o700, (
        f"soul_data_dir should be 0o700, got {oct(stat.S_IMODE(soul_data_stat.st_mode))}"
    )

    for path in (
        settings.reach_out_candidates_file,
        settings.shared_language_file,
        settings.drift_log_file,
        settings.consolidation_ledger_file,
        settings.proactive_delivery_log_file,
        settings.reflections_file,
        settings.milestones_file,
    ):
        if path.exists():
            file_stat = path.stat()
            assert stat.S_IMODE(file_stat.st_mode) == 0o600, (
                f"{path.name} should be 0o600, got {oct(stat.S_IMODE(file_stat.st_mode))}"
            )
