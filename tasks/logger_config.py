#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Feb 10 08:18:26 2026

@author: imchugh
"""

from datetime import datetime, timezone
import uuid
import logging
from logging.handlers import RotatingFileHandler

from tasks.network_logger import JsonFormatter

def generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand = uuid.uuid4().hex[:6]
    return f"{ts}_{rand}"


class RunIDFilter(logging.Filter):
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record):
        record.run_id = self.run_id
        return True


def configure_logger_json(
    log_path: str,
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
    level: int = logging.DEBUG,
    run_id: str | None = None,
    ) -> str:

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
    file_handler.addFilter(run_filter)   # ← attach here
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JsonFormatter())
    console_handler.setLevel(level)
    console_handler.addFilter(run_filter)  # ← and here
    logger.addHandler(console_handler)

    logger.setLevel(level)

    return run_id
