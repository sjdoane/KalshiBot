"""Single place to configure structlog for one-shot scripts and the bot.

Call `configure_logging()` once at the top of any entry point.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path


def configure_logging(
    level: int = logging.INFO,
    *,
    json_mode: bool = False,
    log_file: Path | None = None,
    log_backup_count: int = 14,
) -> None:
    """Initialize structlog with a readable console renderer by default.

    Pass json_mode=True for production deployments where logs ship to a
    collector. Defaults to human-readable output for local Phase 1.5 work.

    log_file (optional): also write log records to this path with daily
    rotation. The parent directory is created if missing. Keeps the
    most recent `log_backup_count` days. This is used by the LIVE bot
    so the operator can review each day's activity offline.
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

    # Route structlog through stdlib logging so the file handler attached
    # below also captures structlog records. Default structlog factory is
    # PrintLoggerFactory which only writes to a stream, bypassing the
    # stdlib root logger.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    stdlib_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )
    handlers: list[logging.Handler] = [logging.StreamHandler(stream=sys.stderr)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file, when="midnight", interval=1,
            backupCount=log_backup_count, encoding="utf-8", utc=True,
        )
        handlers.append(file_handler)
    for h in handlers:
        h.setFormatter(stdlib_formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    for h in handlers:
        root.addHandler(h)
    # Silence httpx/httpcore INFO chatter. Each Kalshi request would
    # otherwise emit a one-line HTTP-Request log; with our 15-minute
    # cadence + 2000-series scan, that's tens of thousands of lines
    # per day in the rotating file. Keep WARN+ from these libraries
    # (errors and rate-limit warnings still visible).
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
