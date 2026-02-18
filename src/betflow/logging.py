from __future__ import annotations

import logging
import sys
from typing import Optional

import structlog


def configure_logging(env: str, level: str = "INFO") -> None:
    """
    Sets up:
      - stdlib logging (for libraries)
      - structlog (for our app)
    """
    # stdlib logging base
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # structlog processors
    processors = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Prettier output in dev; JSON-ish in other envs
    if env.lower() in {"dev", "local"}:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLogger().level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: Optional[str] = None):
    return structlog.get_logger(name or "betflow")
