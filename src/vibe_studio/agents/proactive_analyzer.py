"""ProactiveAnalyzer — timer-based background code analysis engine."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from PySide6.QtCore import QObject, QTimer, Signal

from vibe_studio.agents.dependency_checker import DependencyChecker
from vibe_studio.agents.performance_analyzer import PerformanceAnalyzer
from vibe_studio.agents.security_scanner import SecurityScanner


class ProactiveAnalyzer(QObject):
    """Periodically scans workspace for security, performance, and dependency issues."""

    analysis_completed = Signal(dict)

    def __init__(self, workspace_root: str | Path, interval_minutes: int = 5, parent: QObject | None = None):
        super().__init__(parent)
        self.workspace_root = Path(workspace_root).resolve()
        self.security_scanner = SecurityScanner()
        self.performance_analyzer = PerformanceAnalyzer()
        self.dependency_checker = DependencyChecker()

        self.timer = QTimer(self)
        self.timer.setInterval(interval_minutes * 60 * 1000)
        self.timer.timeout.connect(self.run_analysis)

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def run_analysis(self) -> dict[str, Any]:
        if not self.workspace_root.exists():
            return {}

        sec = self.security_scanner.scan_project(self.workspace_root)
        perf = self.performance_analyzer.scan_project(self.workspace_root)
        deps = self.dependency_checker.scan_project(self.workspace_root)

        result = {
            "security_findings": sec,
            "performance_findings": perf,
            "dependency_findings": deps,
            "total_issues": len(sec) + len(perf) + len(deps),
        }
        self.analysis_completed.emit(result)
        return result
