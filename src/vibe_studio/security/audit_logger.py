"""Audit Logger — full tool-call audit journal with structured JSONL storage.

Every tool execution is recorded with:
  - timestamp, execution_id, tool name, args, result status, duration
  - anonymized path (~ replaces home dir)
  - risk level from tool registry / plugin metadata

Audit log location: ~/.vibe_studio/audit/audit.jsonl
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    timestamp: float
    execution_id: str
    action: str                     # human-readable summary
    tool: str                       # tool name
    args: dict[str, Any]           # sanitized tool args
    path: str                       # anonymized target path
    status: str                     # "success" | "failed" | "denied" | "cancelled"
    duration_ms: float              # execution time in milliseconds
    risk_level: str                 # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class AuditLogger:
    """Logs security audit records to disk as JSONL."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or (Path.home() / ".vibe_studio" / "audit")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"
        self._session_start = time.time()

    # ------------------------------------------------------------------
    # Core logging
    # ------------------------------------------------------------------

    def log_action(
        self,
        user_action: str,
        execution_id: str,
        tool_name: str = "",
        target_path: str = "",
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        risk_level: str = "LOW",
        args: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = AuditRecord(
            timestamp=time.time(),
            execution_id=execution_id,
            action=user_action,
            tool=tool_name,
            args=self._sanitize_args(args or {}),
            path=self._anonymize_path(target_path),
            status=status,
            duration_ms=duration_ms,
            risk_level=risk_level,
            details=details or {},
        )
        self._write(record)

    def log_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        result_status: str,
        execution_id: str,
        duration_ms: float = 0.0,
        risk_level: str = "LOW",
        error: str = "",
    ) -> None:
        """Convenience method for logging a tool call with full args."""
        target_path = str(args.get("path", args.get("filename", args.get("target", ""))))
        self.log_action(
            user_action=f"tool_call:{tool_name}",
            execution_id=execution_id,
            tool_name=tool_name,
            target_path=target_path,
            status=result_status,
            duration_ms=duration_ms,
            risk_level=risk_level,
            args=args,
            details={"error": error} if error else {},
        )

    def log_permission_denied(
        self,
        tool_name: str,
        execution_id: str,
        reason: str = "",
    ) -> None:
        self.log_action(
            user_action=f"permission_denied:{tool_name}",
            execution_id=execution_id,
            tool_name=tool_name,
            status="denied",
            risk_level="HIGH",
            details={"reason": reason},
        )

    def log_security_event(
        self,
        event_type: str,
        execution_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.log_action(
            user_action=f"security:{event_type}",
            execution_id=execution_id,
            status="security_event",
            risk_level="CRITICAL",
            details=details or {},
        )

    # ------------------------------------------------------------------
    # Query / reporting
    # ------------------------------------------------------------------

    def get_session_summary(self) -> dict[str, Any]:
        """Return aggregated stats for the current session."""
        records = self._read_recent(hours=24)
        by_status: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        for r in records:
            by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
            by_tool[r.get("tool", "?")] = by_tool.get(r.get("tool", "?"), 0) + 1
            by_risk[r.get("risk_level", "?")] = by_risk.get(r.get("risk_level", "?"), 0) + 1
        return {
            "total_actions": len(records),
            "by_status": by_status,
            "top_tools": sorted(by_tool.items(), key=lambda x: -x[1])[:10],
            "by_risk": by_risk,
        }

    def _read_recent(self, hours: int = 24) -> list[dict[str, Any]]:
        cutoff = time.time() - hours * 3600
        records: list[dict[str, Any]] = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("timestamp", 0) >= cutoff:
                            records.append(rec)
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass
        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write(self, record: AuditRecord) -> None:
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(record.to_json() + "\n")
        except Exception as exc:
            logger.debug("Audit write failed: %s", exc)

    def _anonymize_path(self, path_str: str) -> str:
        if not path_str:
            return ""
        try:
            home = str(Path.home())
            if path_str.startswith(home):
                return path_str.replace(home, "~", 1)
        except Exception:
            pass
        return path_str

    def _sanitize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive values from args before logging."""
        _sensitive = {"api_key", "password", "secret", "token", "private_key", "auth"}
        sanitized: dict[str, Any] = {}
        for k, v in args.items():
            if any(s in k.lower() for s in _sensitive):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, str) and len(v) > 500:
                sanitized[k] = v[:200] + "...[truncated]"
            else:
                sanitized[k] = v
        return sanitized


default_audit_logger = AuditLogger()
