"""Helpers for rendering startup diagnostics."""

from __future__ import annotations

from soul.bootstrap.validator import StartupReport


def render_startup_report(report: StartupReport) -> list[str]:
    return list(report.diagnostics)
