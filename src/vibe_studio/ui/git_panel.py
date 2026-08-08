"""Git panel — shows status, diff, staged/unstaged files, branch info, commit UI."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class GitPanel(QWidget):
    """Git panel with file change list, diff viewer, and commit/restore actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workspace: str = ""
        self._files: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Branch + refresh row
        top_row = QHBoxLayout()
        self.branch_label = QLabel("Branch: —")
        self.branch_label.setStyleSheet("font-weight: bold; color: #38bdf8;")
        top_row.addWidget(self.branch_label)
        top_row.addStretch()

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setFixedHeight(26)
        refresh_btn.clicked.connect(self._refresh)
        top_row.addWidget(refresh_btn)
        layout.addLayout(top_row)

        # Splitter: [file list] / [diff]
        splitter = QSplitter(Qt.Horizontal)

        # Left: file list + action buttons
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        self.file_list = QListWidget()
        self.file_list.setToolTip("Changed files (click to see diff)")
        self.file_list.itemClicked.connect(self._show_file_diff)
        ll.addWidget(self.file_list)

        # Action buttons
        btn_row = QHBoxLayout()
        stage_btn = QPushButton("Stage All")
        stage_btn.setFixedHeight(26)
        stage_btn.clicked.connect(self._stage_all)

        commit_btn = QPushButton("Commit…")
        commit_btn.setFixedHeight(26)
        commit_btn.setStyleSheet("QPushButton{background:#3b82f6;color:white;border:none;border-radius:4px;}")
        commit_btn.clicked.connect(self._commit)

        restore_btn = QPushButton("Restore")
        restore_btn.setFixedHeight(26)
        restore_btn.setStyleSheet("QPushButton{background:#dc2626;color:white;border:none;border-radius:4px;}")
        restore_btn.clicked.connect(self._restore_selected)

        btn_row.addWidget(stage_btn)
        btn_row.addWidget(commit_btn)
        btn_row.addWidget(restore_btn)
        ll.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: diff viewer
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(__import__("PySide6.QtGui", fromlist=["QFont"]).QFont("monospace", 10))
        splitter.addWidget(self.diff_view)
        splitter.setSizes([200, 500])
        layout.addWidget(splitter)

    # ------------------------------------------------------------------

    def set_git_info(self, status_text: str, diff_text: str, branch: str = "main") -> None:
        self.branch_label.setText(f"Branch: {branch}")
        self.file_list.clear()
        self._files = []
        for line in status_text.splitlines():
            line = line.strip()
            if not line:
                continue
            self.file_list.addItem(line)
            # Extract filename (last token of "XY filename")
            parts = line.split()
            if parts:
                self._files.append(parts[-1])
        self.diff_view.setPlainText(diff_text)

    def _show_file_diff(self, item: QListWidgetItem) -> None:
        # Show per-file diff
        parts = item.text().split()
        if not parts:
            return
        filename = parts[-1]
        main_win = self.window()
        if hasattr(main_win, "show_git_file_diff"):
            main_win.show_git_file_diff(filename)

    def _refresh(self) -> None:
        main_win = self.window()
        if hasattr(main_win, "refresh_git_status"):
            main_win.refresh_git_status()

    def _stage_all(self) -> None:
        workspace = self._get_workspace()
        if not workspace:
            return
        try:
            subprocess.run(["git", "add", "-A"], cwd=workspace, check=False)
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Git Error", str(e))

    def _commit(self) -> None:
        workspace = self._get_workspace()
        if not workspace:
            return
        msg, ok = QInputDialog.getText(self, "Commit", "Commit message:")
        if not ok or not msg.strip():
            return
        try:
            subprocess.run(["git", "add", "-A"], cwd=workspace, check=False)
            result = subprocess.run(
                ["git", "commit", "-m", msg.strip()],
                cwd=workspace, capture_output=True, text=True,
            )
            if result.returncode == 0:
                QMessageBox.information(self, "Committed", result.stdout or "Commit successful.")
            else:
                QMessageBox.warning(self, "Git Error", result.stderr or "Commit failed.")
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Git Error", str(e))

    def _restore_selected(self) -> None:
        workspace = self._get_workspace()
        if not workspace:
            return
        selected = self.file_list.currentItem()
        if not selected:
            return
        parts = selected.text().split()
        filename = parts[-1] if parts else ""
        if not filename:
            return
        reply = QMessageBox.question(
            self, "Restore File",
            f"Restore '{filename}' to last committed state? This discards all changes.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            subprocess.run(["git", "restore", filename], cwd=workspace, check=False)
            self._refresh()

    def _get_workspace(self) -> str:
        main_win = self.window()
        if hasattr(main_win, "settings") and main_win.settings.project_path:
            return main_win.settings.project_path
        return str(Path.cwd())
