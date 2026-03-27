from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "resolve-python.sh"
SHELL = shutil.which("sh") or shutil.which("bash")

pytestmark = pytest.mark.skipif(
    SHELL is None,
    reason="resolve-python.sh tests require a POSIX shell on PATH",
)


def _write_executable(path: Path, content: str = "#!/usr/bin/env sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_resolver(tmp_path: Path, *, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert SHELL is not None
    env = os.environ.copy()
    env["PATH"] = ""
    env.update(extra_env or {})
    return subprocess.run(
        [SHELL, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _resolved_output_path(tmp_path: Path, raw_output: str) -> Path:
    candidate = Path(raw_output.strip())
    if candidate.is_absolute():
        return candidate
    return (tmp_path / candidate).resolve()


def test_resolver_prefers_virtual_env_python_over_path_python3(tmp_path):
    venv_python = tmp_path / ".venv" / "bin" / "python"
    path_python3 = tmp_path / "fake-bin" / "python3"
    _write_executable(venv_python)
    _write_executable(path_python3)

    result = _run_resolver(tmp_path, extra_env={"PATH": str(path_python3.parent)})

    assert result.returncode == 0
    assert _resolved_output_path(tmp_path, result.stdout) == venv_python.resolve()


def test_resolver_prefers_explicit_virtual_env_variable(tmp_path):
    repo_python = tmp_path / ".venv" / "bin" / "python"
    active_python = tmp_path / "active-env" / "bin" / "python"
    _write_executable(repo_python)
    _write_executable(active_python)

    result = _run_resolver(
        tmp_path,
        extra_env={
            "PATH": "",
            "VIRTUAL_ENV": str(active_python.parent.parent),
        },
    )

    assert result.returncode == 0
    assert _resolved_output_path(tmp_path, result.stdout) == active_python.resolve()


def test_resolver_supports_windows_style_local_venv_layout(tmp_path):
    windows_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    _write_executable(windows_python)

    result = _run_resolver(tmp_path)

    assert result.returncode == 0
    assert _resolved_output_path(tmp_path, result.stdout) == windows_python.resolve()


def test_resolver_falls_back_to_path_python3(tmp_path):
    path_python3 = tmp_path / "fake-bin" / "python3"
    _write_executable(path_python3)

    result = _run_resolver(tmp_path, extra_env={"PATH": str(path_python3.parent)})

    assert result.returncode == 0
    assert result.stdout.strip() == "python3"


def test_resolver_errors_when_explicit_python_is_not_executable(tmp_path):
    missing = tmp_path / "missing-python"

    result = _run_resolver(tmp_path, extra_env={"SOUL_PYTHON_BIN": str(missing)})

    assert result.returncode == 1
    assert "SOUL_PYTHON_BIN is set but not executable" in result.stderr


def test_resolver_errors_when_no_python_is_available(tmp_path):
    result = _run_resolver(tmp_path)

    assert result.returncode == 127
    assert "Python was not found" in result.stderr
