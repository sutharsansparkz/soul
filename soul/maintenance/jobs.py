"""Maintenance runner for the SQLite-only runtime.

Supports both manual CLI invocation and automatic trigger-based scheduling
that fires after each chat session ends.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from soul.config import Settings, get_settings
from soul.memory.repositories.maintenance import MaintenanceRunRepository

from .consolidation import consolidate_pending_sessions
from .decay import run_hms_decay
from .drift import derive_resonance_signals, run_drift_task
from .proactive import dispatch_reach_out_candidates, refresh_proactive_candidates
from .reflection import generate_monthly_reflection

_logger = logging.getLogger(__name__)

_last_auto_success: datetime | None = None
_last_auto_failure: datetime | None = None
_auto_in_flight: bool = False
_auto_lock = threading.Lock()


def run_enabled_maintenance(settings: Settings | None = None) -> dict[str, object]:
    resolved_settings = settings or get_settings()
    runs = MaintenanceRunRepository(resolved_settings.database_url)
    summary: dict[str, object] = {}

    consolidation_run = runs.start("consolidation")
    try:
        consolidated = consolidate_pending_sessions(
            database_url=resolved_settings.database_url,
            settings=resolved_settings,
            source="maintenance",
        )
        runs.finish(consolidation_run, status="ok", details={"sessions": len(consolidated)})
        summary["consolidation"] = consolidated
    except Exception as exc:
        runs.finish(consolidation_run, status="failed", error=str(exc))
        raise

    decay_run = runs.start("decay")
    try:
        decay = run_hms_decay(settings=resolved_settings)
        runs.finish(decay_run, status="ok", details=decay)
        summary["decay"] = decay
    except Exception as exc:
        runs.finish(decay_run, status="failed", error=str(exc))
        raise

    if resolved_settings.enable_drift:
        drift_run = runs.start("drift")
        try:
            signals = derive_resonance_signals(resolved_settings.database_url, settings=resolved_settings)
            drift = run_drift_task(resonance_signals=signals, settings=resolved_settings)
            runs.finish(drift_run, status="ok", details=drift)
            summary["drift"] = drift
        except Exception as exc:
            runs.finish(drift_run, status="failed", error=str(exc))
            raise

    if resolved_settings.enable_reflection:
        reflection_run = runs.start("reflection")
        try:
            reflection = generate_monthly_reflection(resolved_settings)
            runs.finish(
                reflection_run,
                status="ok",
                details={"created": bool(reflection), "key": reflection.date if reflection else None},
            )
            summary["reflection"] = reflection.date if reflection else None
        except Exception as exc:
            runs.finish(reflection_run, status="failed", error=str(exc))
            raise

    if resolved_settings.enable_proactive:
        proactive_run = runs.start("proactive")
        try:
            candidates = refresh_proactive_candidates(resolved_settings, channel="cli")
            dispatched = (
                dispatch_reach_out_candidates(resolved_settings, candidates)
                if resolved_settings.enable_telegram
                else {"sent": 0, "delivered_triggers": []}
            )
            runs.finish(
                proactive_run,
                status="ok",
                details={"candidates": len(candidates), "sent": dispatched["sent"]},
            )
            summary["proactive"] = {"candidates": len(candidates), "delivery": dispatched}
        except Exception as exc:
            runs.finish(proactive_run, status="failed", error=str(exc))
            raise

    return summary


def trigger_maintenance_if_due(settings: Settings | None = None) -> None:
    """Run maintenance in a background thread if enough time has elapsed.

    This is designed to be called at session end so that decay, drift,
    and reflection jobs run automatically without a manual CLI command.
    The function is non-blocking and rate-limited to at most once per hour.
    """
    global _auto_in_flight, _last_auto_success, _last_auto_failure
    resolved_settings = settings or get_settings()

    if not resolved_settings.enable_background_jobs:
        return

    now = datetime.now(timezone.utc)
    interval = resolved_settings.maintenance_auto_interval
    failure_backoff_seconds = min(60, interval)  # don't retry too aggressively after failures
    with _auto_lock:
        if _auto_in_flight:
            _logger.debug("Skipping auto-maintenance: already in flight")
            return

        if _last_auto_success is not None:
            elapsed_success = (now - _last_auto_success).total_seconds()
            if elapsed_success < interval:
                _logger.debug(
                    "Skipping auto-maintenance: last success was %.0fs ago (threshold: %ds)",
                    elapsed_success,
                    interval,
                )
                return

        if _last_auto_failure is not None:
            elapsed_failure = (now - _last_auto_failure).total_seconds()
            if elapsed_failure < failure_backoff_seconds:
                _logger.debug(
                    "Skipping auto-maintenance: last failure was %.0fs ago (backoff: %ds)",
                    elapsed_failure,
                    failure_backoff_seconds,
                )
                return

        _auto_in_flight = True

    thread = threading.Thread(
        target=_run_maintenance_safe,
        args=(resolved_settings,),
        name="soul-maintenance-trigger",
        daemon=True,
    )
    thread.start()
    _logger.info("Triggered background maintenance run")


def _run_maintenance_safe(settings: Settings) -> None:
    """Execute maintenance and swallow exceptions to avoid crashing daemon threads."""
    global _auto_in_flight, _last_auto_success, _last_auto_failure
    try:
        summary = run_enabled_maintenance(settings)
        _logger.info("Background maintenance completed: %s", summary)
        with _auto_lock:
            _last_auto_success = datetime.now(timezone.utc)
            _auto_in_flight = False
    except Exception:
        _logger.exception("Background maintenance failed")
        with _auto_lock:
            _last_auto_failure = datetime.now(timezone.utc)
            _auto_in_flight = False
