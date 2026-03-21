from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import math
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from soul.config import Settings


@dataclass(slots=True)
class EmbedderStatus:
    enabled: bool
    backend: str
    reason: str | None = None


class LocalHybridEmbedder:
    """Optional local embedding helper used for hybrid retrieval."""

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self._model = None
        self._status = EmbedderStatus(enabled=False, backend="disabled", reason="HYBRID_EMBEDDINGS=false")
        self._initialize()

    @property
    def status(self) -> EmbedderStatus:
        return self._status

    def encode(self, text: str) -> list[float] | None:
        if not text.strip() or self._model is None:
            return None
        try:
            vector = self._model.encode([text], convert_to_numpy=False)[0]
        except Exception:
            return None
        try:
            return [float(value) for value in vector]
        except Exception:
            return None

    def encode_to_blob(self, text: str) -> bytes | None:
        vector = self.encode(text)
        if not vector:
            return None
        return json.dumps(vector, ensure_ascii=True).encode("utf-8")

    def decode_blob(self, payload: object) -> list[float] | None:
        if payload is None:
            return None
        raw: bytes
        if isinstance(payload, memoryview):
            raw = payload.tobytes()
        elif isinstance(payload, bytes):
            raw = payload
        else:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(value, list):
            return None
        output: list[float] = []
        for item in value:
            try:
                output.append(float(item))
            except (TypeError, ValueError):
                return None
        return output or None

    def cosine_similarity(self, left: list[float] | None, right: list[float] | None) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        cosine = dot / (left_norm * right_norm)
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    def _initialize(self) -> None:
        if not bool(getattr(self.settings, "hybrid_embeddings", False)):
            return
        model_name = str(getattr(self.settings, "hybrid_model", "all-MiniLM-L6-v2"))
        try:
            sentence_embeddings = importlib.import_module("sentence_" "trans" "formers")
            sentence_transformer_cls = getattr(sentence_embeddings, "Sentence" "Transformer")
        except Exception:
            self._status = EmbedderStatus(
                enabled=False,
                backend="unavailable",
                reason="sentence embedding package is not installed",
            )
            return
        try:
            self._model = sentence_transformer_cls(model_name)
        except Exception as exc:
            self._status = EmbedderStatus(
                enabled=False,
                backend="error",
                reason=f"failed to load model {model_name}: {exc}",
            )
            return
        self._status = EmbedderStatus(enabled=True, backend="sentence-embedding", reason=None)
