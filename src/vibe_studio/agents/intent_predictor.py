"""IntentPredictor — command history tracker and next-step command completion generator."""
from __future__ import annotations


class IntentPredictor:
    """Predicts next probable user actions and commands based on history and project state."""

    SUGGESTION_MAP: dict[str, list[str]] = {
        "npm install": ["npm start", "npm test", "npm run dev", "npm run build"],
        "pip install": ["pytest", "python -m build", "ruff check ."],
        "git add": ["git commit -m 'Update code'", "git status", "git diff"],
        "git status": ["git diff", "git add .", "git log -5"],
        "git": ["git status", "git diff", "git log -5", "git branch"],
        "pytest": ["pytest -v", "ruff check .", "ruff format ."],
        "cargo build": ["cargo test", "cargo run", "cargo check"],
        "go build": ["go test ./...", "go run main.go"],
    }

    def __init__(self):
        self.history: list[str] = []

    def record_command(self, command: str) -> None:
        cmd = command.strip()
        if cmd:
            self.history.append(cmd)
            if len(self.history) > 100:
                self.history.pop(0)

    def predict_next(self, current_input: str = "") -> list[str]:
        inp = current_input.strip().lower()
        if not inp and self.history:
            last = self.history[-1].lower()
            for key, suggestions in self.SUGGESTION_MAP.items():
                if key in last:
                    return suggestions

        if inp:
            for key, suggestions in self.SUGGESTION_MAP.items():
                if inp == key or inp.startswith(key):
                    return suggestions

        return ["git status", "pytest", "ruff check ."]
