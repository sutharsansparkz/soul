"""Maintenance runner for the SQLite-only runtime."""

from __future__ import annotations

from soul.config import Settings, get_settings
from soul.memory.repositories.maintenance import MaintenanceRunRepository

from .consolidation import consolidate_pending_sessions
from .decay import run_hms_decay
from .drift import derive_resonance_signals, run_drift_task
from .proactive import dispatch_reach_out_candidates, refresh_proactive_candidates
from .reflection import generate_monthly_reflection


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
