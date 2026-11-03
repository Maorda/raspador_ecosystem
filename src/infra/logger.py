"""Logging estructurado con biblioteca estándar; no depende de structlog."""
from __future__ import annotations
import json
import logging
import sys
import traceback
from typing import Any


def configure_logging(json_logs: bool = True, log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


class StructuredLogger:
    def __init__(self, name: str, context: dict[str, Any] | None = None) -> None:
        self._logger = logging.getLogger(name)
        self._context = dict(context or {})

    def bind(self, **context: Any) -> "StructuredLogger":
        return StructuredLogger(self._logger.name, {**self._context, **context})

    def _emit(self, level: int, event: str, **fields: Any) -> None:
        exc_info = fields.pop("exc_info", False)
        if exc_info:
            fields["exception"] = traceback.format_exc()
        payload = {**self._context, **fields, "event": event}
        self._logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))

    def debug(self, event: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, **fields)

    def exception(self, event: str, **fields: Any) -> None:
        fields["exc_info"] = True
        self._emit(logging.ERROR, event, **fields)


def get_logger(name: str, **initial_values: Any) -> StructuredLogger:
    return StructuredLogger(name, initial_values)
