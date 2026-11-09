"""Structured JSON logging to stdout (one object per line), suitable for any hosting platform's log collector.

Never logs request bodies, query strings, tokens, or raw client addresses (a short one-way hash is logged so repeated
callers can be correlated without storing the address).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time

LOGGER = logging.getLogger("athar")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
               "level": record.levelname.lower(), "msg": record.getMessage()}
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            out.update(extra)
        if record.exc_info:
            out["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"   # no traceback/internals
        return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def setup() -> None:
    level = os.environ.get("ATHAR_LOG_LEVEL", "INFO").upper()
    LOGGER.setLevel(level if level in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO")
    if not any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JsonFormatter) for h in LOGGER.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        LOGGER.addHandler(handler)
    LOGGER.propagate = False


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def log(msg: str, level: int = logging.INFO, **fields: object) -> None:
    LOGGER.log(level, msg, extra={"fields": fields})
