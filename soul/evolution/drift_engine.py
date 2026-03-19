from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import json


SOUL_BASELINE: dict[str, float] = {
    "humor_intensity": 0.5,
    "response_length": 0.5,
    "curiosity_depth": 0.5,
    "directness": 0.5,
    "warmth_expression": 0.5,
}

MAX_DRIFT = 0.20
WEEKLY_RATE = 0.01


@dataclass(slots=True)
class DriftRun:
    run_date: str
    dimensions_before: dict[str, float]
    dimensions_after: dict[str, float]
    resonance_signals: dict[str, float]
    notes: str = ""


def run_weekly_drift(current: dict[str, float], resonance_signals: dict[str, float]) -> dict[str, float]:
    current = merge_with_baseline(current)
    updated: dict[str, float] = {}
    for dimension, value in current.items():
        signal = resonance_signals.get(dimension, 0.0)
        baseline = SOUL_BASELINE.get(dimension, value)
        new_value = value + (signal * WEEKLY_RATE)
        lower = baseline - MAX_DRIFT
        upper = baseline + MAX_DRIFT
        updated[dimension] = round(max(lower, min(upper, new_value)), 4)
    return updated


def merge_with_baseline(current: dict[str, float] | None) -> dict[str, float]:
    merged = dict(SOUL_BASELINE)
    if current:
        for key, value in current.items():
            if key in SOUL_BASELINE:
                merged[key] = float(value)
    return merged


class DriftLogRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[DriftRun]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        migrated = False
        runs: list[DriftRun] = []
        for item in payload:
            record = dict(item)
            if not _is_iso_date(record.get("run_date")):
                record["run_date"] = datetime.now(timezone.utc).date().isoformat()
                migrated = True
            runs.append(DriftRun(**record))
        if migrated:
            self.save(runs)
        return runs

    def save(self, runs: list[DriftRun]) -> None:
        payload = [asdict(run) for run in runs]
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True
