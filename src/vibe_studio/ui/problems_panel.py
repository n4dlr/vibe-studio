"""Problems panel — parse ruff/mypy/eslint/pytest output, click to navigate."""
from __future__ import annotations

import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# Parsers for common linter/type-checker output formats
_RUFF_RE   = re.compile(r'^([\w./\\-]+):(\d+):(\d+):\s+([A-Z]\d+)\s+(.*)')
_MYPY_RE   = re.compile(r'^([\w./\\-]+):(\d+):\s+(error|warning|note):\s+(.*)')
_ESLINT_RE = re.compile(r'^\s+([\d]+):(\d+)\s+(error|warning)\s+(.*)')
_PYTEST_RE = re.compile(r'^(FAILED|ERROR)\s+([\w./\\:-]+)(?:\s+-\s+(.*))?$')
_GENERIC_RE = re.compile(r'^([\w./\\-]+\.[\w]+):(\d+)(?::(\d+))?[:\s]+(.*(?:error|warning|failed).*)', re.I)


def parse_linter_output(output: str, source: str = "") -> list[dict]:
    """Convert raw linter/test output into structured problem records."""
    problems: list[dict] = []

    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue

        # ruff: src/foo.py:10:5: E501 line too long
        m = _RUFF_RE.match(line)
        if m:
            problems.append({
                "severity": "Error" if m.group(4)[0] == "E" else "Warning",
                "message": f"{m.group(4)} {m.group(5)}",
                "file": m.group(1),
                "line": int(m.group(2)),
                "col": int(m.group(3)),
                "source": source or "ruff",
            })
            continue

        # mypy: src/foo.py:10: error: ...
        m = _MYPY_RE.match(line)
        if m:
            sev = "Error" if m.group(3) == "error" else "Warning" if m.group(3) == "warning" else "Info"
            problems.append({
                "severity": sev,
                "message": m.group(4),
                "file": m.group(1),
                "line": int(m.group(2)),
                "col": 0,
                "source": source or "mypy",
            })
            continue

        # pytest FAILED
        m = _PYTEST_RE.match(line)
        if m:
            kind = m.group(1)
            loc = m.group(2)
            msg = m.group(3) or ""
            file_part = loc.split("::")[0]
            problems.append({
                "severity": kind,
                "message": msg or loc,
                "file": file_part,
                "line": 0,
                "col": 0,
                "source": source or "pytest",
            })
            continue

        # Generic: file.py:10: error: ...
        m = _GENERIC_RE.match(line)
        if m:
            sev = "Warning" if "warning" in line.lower() else "Error"
            problems.append({
                "severity": sev,
                "message": m.group(4),
                "file": m.group(1),
                "line": int(m.group(2)) if m.group(2) else 0,
                "col": int(m.group(3)) if m.group(3) else 0,
                "source": source or "unknown",
            })

    return problems


class ProblemsPanel(QWidget):
    """Problems panel with click-to-navigate and AI-fix button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.count_label = QLabel("0 Problems")
        self.count_label.setStyleSheet("font-weight: bold; color: #94a3b8;")

        self.fix_btn = QPushButton("Ask AI to Fix All")
        self.fix_btn.setStyleSheet(
            "QPushButton{background:#3b82f6;color:white;border:none;"
            "border-radius:6px;padding:6px 12px;font-weight:bold;}"
            "QPushButton:hover{background:#2563eb;}"
        )
        self.fix_btn.clicked.connect(self._trigger_ai_fix)

        top_row.addWidget(self.count_label)
        top_row.addStretch()
        top_row.addWidget(self.fix_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Severity", "Message", "File", "Line", "Source"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(
            "QTableWidget{background:#0a1016;color:#e6edf7;border:1px solid #202a36;}"
            "QHeaderView::section{background:#171d26;color:#94a3b8;border:none;padding:4px;}"
            "QTableWidget::item:selected{background:#1d3557;}"
        )
        # Double-click navigates to the problem location
        self.table.itemDoubleClicked.connect(self._navigate_to_problem)
        layout.addWidget(self.table)

    # ------------------------------------------------------------------

    def set_problems(self, problems: list[dict]) -> None:
        self.table.setRowCount(0)
        errors = sum(1 for p in problems if "error" in p.get("severity", "").lower() or p.get("severity") in ("FAILED", "ERROR"))
        warnings = len(problems) - errors
        label_parts = []
        if errors:
            label_parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if warnings:
            label_parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
        self.count_label.setText(", ".join(label_parts) or "0 Problems")

        for p in problems:
            row = self.table.rowCount()
            self.table.insertRow(row)
            sev = p.get("severity", "Error")
            sev_item = QTableWidgetItem(sev)
            colour = "#f87171" if sev in ("Error", "FAILED", "ERROR") else "#fbbf24"
            sev_item.setForeground(__import__("PySide6.QtGui", fromlist=["QColor"]).QColor(colour))
            self.table.setItem(row, 0, sev_item)
            self.table.setItem(row, 1, QTableWidgetItem(p.get("message", "")))
            self.table.setItem(row, 2, QTableWidgetItem(p.get("file", "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(p.get("line", ""))))
            self.table.setItem(row, 4, QTableWidgetItem(p.get("source", "")))

    def add_from_output(self, output: str, source: str = "") -> None:
        """Parse raw linter/test output and display problems."""
        problems = parse_linter_output(output, source)
        self.set_problems(problems)

    def _navigate_to_problem(self, item: QTableWidgetItem) -> None:
        row = item.row()
        file_item = self.table.item(row, 2)
        line_item = self.table.item(row, 3)
        if not file_item:
            return
        file_path = file_item.text()
        try:
            line = int(line_item.text()) if line_item and line_item.text() else 1
        except ValueError:
            line = 1
        main_win = self.window()
        if hasattr(main_win, "open_editor") and file_path:
            from pathlib import Path
            root = Path(getattr(getattr(main_win, "settings", None), "project_path", "") or ".")
            full = root / file_path
            if full.exists():
                main_win.open_editor(full, goto_line=line)

    def _trigger_ai_fix(self) -> None:
        main_win = self.window()
        if hasattr(main_win, "trigger_ai_action"):
            main_win.trigger_ai_action("fix_problems", "", "")
