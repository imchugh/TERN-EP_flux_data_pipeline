#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Feb 10 08:20:17 2026

@author: imchugh
"""

import logging
import json
import time

class JsonFormatter(logging.Formatter):
    """Formats logs as one JSON object per line, including all extra fields."""

    def format(self, record):
        log_record = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)
                ),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Include structured extra fields (task, site, latency, etc.)
        for key, value in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "levelname", "levelno",
                "lineno", "module", "msecs", "message", "msg",
                "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
            ):
                log_record[key] = value

        # Include exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)