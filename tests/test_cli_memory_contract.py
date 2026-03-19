from __future__ import annotations

from typer.testing import CliRunner

import soul.cli as cli


def test_memory_subcommands_include_hms_surface():
    result = CliRunner().invoke(cli.app, ["memories", "--help"])

    assert result.exit_code == 0
    assert "search" in result.stdout
    assert "top" in result.stdout
    assert "cold" in result.stdout
    assert "boost" in result.stdout
    assert "clear" in result.stdout
