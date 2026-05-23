"""Single place to configure structlog for one-shot scripts and the bot.

Call `configure_logging()` once at the top of any entry point.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO, *, json_mode: bool = False) -> None:
    """Initialize structlog with a readable console renderer by default.

    Pass json_mode=True for production deployments where logs ship to a
    collector. Defaults to human-readable output for local Phase 1.5 work.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    if json_mode:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(stream=sys.stderr, level=level, format="%(message)s")
