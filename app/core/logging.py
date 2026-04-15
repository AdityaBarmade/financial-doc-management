"""
app/core/logging.py — Structured Logging Configuration

Uses Loguru for rich, structured logging with:
- Console output (colored)
- File rotation (daily, max 10 days)
- JSON-compatible format for production
"""

import sys
import io
from loguru import logger
from app.core.config import settings


def setup_logging():
    """Configure Loguru logger for the application."""
    # Remove default handler
    logger.remove()

    # Force UTF-8 output on Windows to support emoji/unicode log messages
    if sys.platform == "win32":
        safe_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    else:
        safe_stdout = sys.stdout

    # ─── Console Handler ──────────────────────────────────────────────────────
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    logger.add(
        safe_stdout,
        format=log_format,
        level=settings.LOG_LEVEL,
        colorize=False,   # Disable colorize with custom stream wrapper
        backtrace=True,
        diagnose=settings.DEBUG,
    )

    # ─── File Handler ─────────────────────────────────────────────────────────
    logger.add(
        settings.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level=settings.LOG_LEVEL,
        rotation="1 day",
        retention="10 days",
        compression="zip",
        backtrace=True,
        diagnose=False,  # Disable in file for security
        enqueue=True,    # Thread-safe async logging
    )


def get_logger(name: str):
    """Get a named logger instance."""
    return logger.bind(name=name)
