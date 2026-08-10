#!/usr/bin/env python3
"""JSON rotating-file + console logger setup, with run-id tagging."""

import logging
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from tasks.network_logger import JsonFormatter


def generate_run_id() -> str:
    """Return a sortable, near-unique run id: UTC timestamp + 6 random hex chars."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rand = uuid.uuid4().hex[:6]
    return f"{ts}_{rand}"


class RunIDFilter(logging.Filter):
    """Logging filter that stamps every record with a fixed run_id."""

    def __init__(self, run_id: str):
        """Bind the run_id to stamp onto every filtered record."""
        super().__init__()
        self.run_id = run_id

    def filter(self, record):
        """Attach run_id to the record and always allow it through."""
        record.run_id = self.run_id
        return True


def configure_logger_json(
    log_path: str,
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
    level: int = logging.DEBUG,
    run_id: str | None = None,
) -> str:
    """Configure the root logger with JSON-formatted file + console handlers.

    Args:
        log_path: destination path for the rotating log file.
        max_bytes: rotate the log file once it exceeds this size.
        backup_count: number of rotated backups to keep.
        level: logging level applied to both handlers and the root logger.
        run_id: run identifier stamped on every record. Generated via
            `generate_run_id` if not provided.

    Returns:
        The run_id used (generated or passed through).
    """
    if run_id is None:
        run_id = generate_run_id()

    logger = logging.getLogger()
    logger.handlers.clear()
    logger.filters.clear()

    run_filter = RunIDFilter(run_id)

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.setLevel(level)
    file_handler.addFilter(run_filter)  # ← attach here
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JsonFormatter())
    console_handler.setLevel(level)
    console_handler.addFilter(run_filter)  # ← and here
    logger.addHandler(console_handler)

    logger.setLevel(level)

    return run_id
