"""Strict parser helpers for structured LLM payloads."""

from __future__ import annotations

import json

from soul.bootstrap.errors import ExtractionValidationError


def parse_json_object(text: str) -> dict[str, object]:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ExtractionValidationError(f"Expected a JSON object, got: {text!r}") from exc
    if not isinstance(payload, dict):
        raise ExtractionValidationError("Expected a JSON object payload.")
    return payload
