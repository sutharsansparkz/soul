from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math


@dataclass(slots=True)
class HMSComponents:
    score_emotional: float
    score_retrieval: float
    score_temporal: float
    score_flagged: float
    score_volume: float
    hms_score: float
    tier: str
    decay_rate: float


EMOTION_INTENSITY_MAP: dict[str, float] = {
    "overwhelmed": 0.95,
    "stressed": 0.85,
    "venting": 0.80,
    "celebrating": 0.75,
    "reflective": 0.60,
    "curious": 0.45,
    "neutral": 0.10,
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def decay_rate_from_halflife(half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return math.log(2) / half_life_days


def score_temporal(
    *,
    memory_timestamp: str,
    now: datetime | None = None,
    half_life_days: float = 30.0,
) -> float:
    now = now or datetime.now(timezone.utc)
    try:
        created_at = datetime.fromisoformat(memory_timestamp)
    except ValueError:
        return 0.5
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86_400)
    if half_life_days <= 0:
        return 0.0
    return clamp01(math.exp(-math.log(2) * age_days / half_life_days))


def score_retrieval(ref_count: int) -> float:
    # Normalized rehearsal signal; asymptotes near 1.0.
    return clamp01(math.log1p(max(0, ref_count)) / math.log1p(20))


def score_volume(word_count: int) -> float:
    # 120 words ~= full signal.
    return clamp01(max(0, word_count) / 120.0)


def score_emotional(emotional_tag: str | None, explicit_value: float | None = None) -> float:
    if explicit_value is not None:
        return clamp01(explicit_value)
    if emotional_tag is None:
        return EMOTION_INTENSITY_MAP["neutral"]
    return EMOTION_INTENSITY_MAP.get(emotional_tag.casefold(), EMOTION_INTENSITY_MAP["neutral"])


def determine_tier(hms_score: float, cold_threshold: float = 0.05) -> str:
    score = clamp01(hms_score)
    if score < cold_threshold:
        return "cold"
    if score >= 0.75:
        return "vivid"
    if score >= 0.40:
        return "present"
    return "fading"


def compute_composite(
    *,
    score_emotional: float,
    score_retrieval: float,
    score_temporal: float,
    score_flagged: float,
    score_volume: float,
) -> float:
    return clamp01(
        (clamp01(score_emotional) * 0.35)
        + (clamp01(score_retrieval) * 0.25)
        + (clamp01(score_temporal) * 0.20)
        + (clamp01(score_flagged) * 0.10)
        + (clamp01(score_volume) * 0.10)
    )


def initial_components(
    *,
    emotional_tag: str | None,
    memory_timestamp: str,
    word_count: int,
    flagged: bool = False,
    now: datetime | None = None,
    half_life_days: float = 30.0,
    score_emotional_override: float | None = None,
) -> HMSComponents:
    value_emotional = score_emotional(emotional_tag, explicit_value=score_emotional_override)
    value_retrieval = 0.0
    value_temporal = score_temporal(memory_timestamp=memory_timestamp, now=now, half_life_days=half_life_days)
    value_flagged = 1.0 if flagged else 0.0
    value_volume = score_volume(word_count)
    hms_score = compute_composite(
        score_emotional=value_emotional,
        score_retrieval=value_retrieval,
        score_temporal=value_temporal,
        score_flagged=value_flagged,
        score_volume=value_volume,
    )
    return HMSComponents(
        score_emotional=value_emotional,
        score_retrieval=value_retrieval,
        score_temporal=value_temporal,
        score_flagged=value_flagged,
        score_volume=value_volume,
        hms_score=hms_score,
        tier=determine_tier(hms_score),
        decay_rate=decay_rate_from_halflife(half_life_days),
    )


def recompute_components(
    *,
    emotional_tag: str | None,
    memory_timestamp: str,
    word_count: int,
    ref_count: int,
    flagged: bool,
    now: datetime | None = None,
    half_life_days: float = 30.0,
    cold_threshold: float = 0.05,
    score_emotional_override: float | None = None,
) -> HMSComponents:
    value_emotional = score_emotional(emotional_tag, explicit_value=score_emotional_override)
    value_retrieval = score_retrieval(ref_count)
    value_temporal = score_temporal(memory_timestamp=memory_timestamp, now=now, half_life_days=half_life_days)
    value_flagged = 1.0 if flagged else 0.0
    value_volume = score_volume(word_count)
    hms_score = compute_composite(
        score_emotional=value_emotional,
        score_retrieval=value_retrieval,
        score_temporal=value_temporal,
        score_flagged=value_flagged,
        score_volume=value_volume,
    )
    return HMSComponents(
        score_emotional=value_emotional,
        score_retrieval=value_retrieval,
        score_temporal=value_temporal,
        score_flagged=value_flagged,
        score_volume=value_volume,
        hms_score=hms_score,
        tier=determine_tier(hms_score, cold_threshold=cold_threshold),
        decay_rate=decay_rate_from_halflife(half_life_days),
    )


def boosted_components(
    *,
    emotional_tag: str | None,
    memory_timestamp: str,
    word_count: int,
    ref_count: int,
    now: datetime | None = None,
    half_life_days: float = 30.0,
    cold_threshold: float = 0.05,
    score_emotional_override: float | None = None,
) -> HMSComponents:
    return recompute_components(
        emotional_tag=emotional_tag,
        memory_timestamp=memory_timestamp,
        word_count=word_count,
        ref_count=ref_count,
        flagged=True,
        now=now,
        half_life_days=half_life_days,
        cold_threshold=cold_threshold,
        score_emotional_override=score_emotional_override,
    )
