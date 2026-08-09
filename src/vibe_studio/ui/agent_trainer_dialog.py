"""Agent Trainer Dialog — GUI panel for manual few-shot pattern learning into GlobalMemory.

Pillar 4 (UX - Agent Trainer):
  Allows users to manually teach the AI agent by entering prompt keywords and
  ideal solution patterns directly into GlobalMemory.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from vibe_studio.core.global_memory import GlobalMemory


class AgentTrainerDialog(QDialog):
    """Dialog for registering manual pattern rules into GlobalMemory."""

    def __init__(self, parent=None, global_memory: GlobalMemory | None = None) -> None:
        super().__init__(parent)
        self.global_memory = global_memory or GlobalMemory()
        self.setWindowTitle("🎓 Agent Trainer — Teach Global Memory")
        self.setMinimumSize(500, 380)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Teach Vibe Studio a reusable solution pattern. "
            "The agent will automatically recall this pattern for similar future prompts."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(info_label)

        form = QFormLayout()

        self.framework_combo = QComboBox()
        self.framework_combo.addItems(["general", "python", "pyside6", "react", "django", "fastapi", "pytest"])
        self.framework_combo.setEditable(True)
        form.addRow("Framework / Tech:", self.framework_combo)

        self.pattern_type_combo = QComboBox()
        self.pattern_type_combo.addItems(["fix", "convention", "architecture", "snippet", "testing"])
        self.pattern_type_combo.setEditable(True)
        form.addRow("Pattern Type:", self.pattern_type_combo)

        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("e.g. login error handling, dark theme gradient")
        form.addRow("Prompt Keywords:", self.keyword_input)

        self.solution_text = QTextEdit()
        self.solution_text.setPlaceholderText("Describe the ideal solution, approach, or code pattern to follow...")
        form.addRow("Ideal Solution:", self.solution_text)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        save_btn = QPushButton("Save to Global Memory")
        save_btn.setStyleSheet("background-color: #3b82f6; color: white; font-weight: bold;")
        save_btn.clicked.connect(self._save_pattern)
        buttons.addWidget(save_btn)

        layout.addLayout(buttons)

    def _save_pattern(self) -> None:
        framework = self.framework_combo.currentText().strip()
        pattern_type = self.pattern_type_combo.currentText().strip()
        keyword = self.keyword_input.text().strip()
        solution = self.solution_text.toPlainText().strip()

        if not keyword or not solution:
            QMessageBox.warning(self, "Validation Error", "Prompt Keywords and Ideal Solution fields are required.")
            return

        try:
            self.global_memory.record_pattern(
                framework=framework,
                pattern_type=pattern_type,
                keyword=keyword,
                solution=solution,
            )
            QMessageBox.information(
                self, "Success", "Pattern recorded into Global Memory successfully!"
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save pattern: {exc}")
