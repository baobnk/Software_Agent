"""Centralized loguru logger for BnK pipeline.

Usage:
    from tools.logger import log

All sink/format is configured here. Import `log` everywhere else.
"""
import sys
from loguru import logger as log

# Remove default sink
log.remove()

# Console sink — color + clean format
log.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[ctx]: <20}</cyan> | "
        "{message}"
    ),
    colorize=True,
    level="DEBUG",
)

# File sink — full detail, auto-rotate 10MB
log.add(
    "logs/pipeline_{time:YYYYMMDD_HHmmss}.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[ctx]: <20} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
    colorize=False,
    delay=True,  # only create file when first log is written
)

# Bind a default ctx so callers that don't bind still work
log = log.bind(ctx="pipeline")

__all__ = ["log"]
