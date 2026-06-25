"""Structured logging + high-priority alerting for the enterprise layer.

Logs are emitted as single-line JSON so they drop straight into CloudWatch /
Datadog / Loki without a parser. ``alert()`` raises the severity to CRITICAL and
tags the record with ``alert=True`` so an alerting rule can page on it (e.g. a
poison pill hitting the dead-letter queue, or a stranded conversation being
force-purged).
"""
from __future__ import annotations

import json
import logging
import sys

from ..contracts import utcnow

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": utcnow(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # structured fields passed via logger.<level>(..., extra={"fields": {...}})
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if getattr(record, "alert", False):
            payload["alert"] = True
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger("voclyp.enterprise")
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"voclyp.enterprise.{name}")


def alert(logger: logging.Logger, message: str, **fields) -> None:
    """High-priority system alert (CRITICAL + alert=True for paging rules)."""
    logger.critical(message, extra={"alert": True, "fields": fields})
