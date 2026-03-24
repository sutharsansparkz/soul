"""Structured logging setup for the strict bootstrap path."""

from __future__ import annotations

import logging

from soul.config import Settings


def configure_logging(settings: Settings) -> None:
    level_name = "DEBUG" if settings.environment == "development" else "INFO"
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
