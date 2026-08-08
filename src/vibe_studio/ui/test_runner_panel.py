from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TestRunnerPanel(QWidget):
    """Test runner panel with status dashboard and one-click 'Run Tests & Fix' button."""

    __test__ = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        top_row = QHBoxLayout()
        self.status_label = QLabel("Tests: Not executed")
        self.status_label.setStyleSheet("font-weight: bold; color: #94a3b8;")

        self.run_btn = QPushButton("Run Tests")
        self.run_btn.setStyleSheet("QPushButton { background: #1d2632; color: #eaf3ff; border: 1px solid #2b3341; border-radius: 6px; padding: 6px 12px; } QPushButton:hover { background: #222e3b; }")
        self.run_btn.clicked.connect(self._run_tests)

        self.run_fix_btn = QPushButton("Run Tests & Fix AI")
        self.run_fix_btn.setStyleSheet("QPushButton { background: #16a34a; color: white; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; } QPushButton:hover { background: #15803d; }")
        self.run_fix_btn.clicked.connect(self._run_tests_and_fix)

        top_row.addWidget(self.status_label)
        top_row.addStretch()
        top_row.addWidget(self.run_btn)
        top_row.addWidget(self.run_fix_btn)
        layout.addLayout(top_row)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFontFamily("monospace")
        self.output_text.setStyleSheet("QTextEdit { background: #0a1016; color: #e6edf7; border: 1px solid #202a36; border-radius: 6px; }")

        layout.addWidget(self.output_text)

    def set_output(self, text: str, passed: bool = True):
        self.output_text.setPlainText(text)
        if passed:
            self.status_label.setText("Tests: PASSED")
            self.status_label.setStyleSheet("font-weight: bold; color: #4ade80;")
        else:
            self.status_label.setText("Tests: FAILED")
            self.status_label.setStyleSheet("font-weight: bold; color: #f87171;")

    def _run_tests(self):
        main_win = self.window()
        if hasattr(main_win, "run_project_tests"):
            main_win.run_project_tests()

    def _run_tests_and_fix(self):
        main_win = self.window()
        if hasattr(main_win, "trigger_ai_action"):
            main_win.trigger_ai_action("run_tests_and_fix", "", "")
