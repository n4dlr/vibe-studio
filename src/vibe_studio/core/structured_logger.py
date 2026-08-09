"""Structured Logger for Vibe Studio.

Produces parseable JSON logs enriched with execution_id, operation_id, state, tokens, and duration.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional


class StructuredLogger:
    """JSON structured logger for agent telemetry and audit trails."""

    def __init__(self, name: str = "vibe_studio"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def log_event(
        self,
        event_type: str,
        execution_id: str,
        operation_id: str = "",
        state: str = "",
        duration: float = 0.0,
        tokens_used: int = 0,
        tool_calls_count: int = 0,
        error_details: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "timestamp": time.time(),
            "event": event_type,
            "execution_id": execution_id,
            "operation_id": operation_id,
            "state": state,
            "duration": round(duration, 4),
            "tokens_used": tokens_used,
            "tool_calls_count": tool_calls_count,
        }
        if error_details:
            payload["error"] = error_details
        if extra:
            payload["extra"] = extra

        self.logger.info(json.dumps(payload))


default_structured_logger = StructuredLogger()
