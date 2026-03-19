from __future__ import annotations

from soul.config import Settings
from soul.memory.embedder import LocalHybridEmbedder


def test_embedder_disabled_by_default(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    embedder = LocalHybridEmbedder(settings)
    assert embedder.status.enabled is False


def test_embedder_blob_decode_handles_invalid_payload(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'soul.db').as_posix()}",
        soul_data_path=str(tmp_path / "soul_data"),
    )
    embedder = LocalHybridEmbedder(settings)
    assert embedder.decode_blob(b"not-json") is None
