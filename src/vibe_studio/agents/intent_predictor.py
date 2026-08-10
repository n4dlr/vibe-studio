"""IntentPredictor — command history tracker, next-step completion, and task verification plan derivation."""
from __future__ import annotations

import re
from vibe_studio.agents.task_verifier import (
    BehaviorRequirement,
    FileRequirement,
    SymbolRequirement,
    TaskRequirement,
    TestRequirement,
)


class IntentPredictor:
    """Predicts next probable user actions and derives verification plans from user task prompts."""

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

    def derive_verification_requirements(self, prompt: str, provider: Any = None) -> TaskRequirement:
        """Derive structured TaskRequirement verification plan from natural language prompt."""
        p_lower = prompt.lower().strip()

        file_reqs: list[FileRequirement] = []
        symbol_reqs: list[SymbolRequirement] = []
        behavior_reqs: list[BehaviorRequirement] = []
        test_reqs: list[TestRequirement] = []

        # 1. Extract explicit filenames (e.g., hello.py, main.ts, index.html)
        file_matches = re.findall(r"[\w/\-]+\.(?:py|js|ts|tsx|jsx|php|vue|go|rs|c|cpp|h|hpp|java|kt|cs|sh|txt|md|html|css|json|yaml|yml|toml)\b", prompt, re.IGNORECASE)
        for fmatch in file_matches:
            if fmatch.lower() in ("e.g.", "i.e.", "vs."):
                continue
            is_delete = any(k in p_lower for k in ["delete", "sil", "remove", "kaldır", "удалить"]) and fmatch.lower() in p_lower
            file_reqs.append(FileRequirement(
                path=fmatch,
                must_exist=not is_delete,
                must_not_exist=is_delete,
                min_size_bytes=1 if not is_delete else 0,
            ))

        # 2. Extract explicit symbol names (e.g. farewell(), def login, class UserProfile, funksiya farewell)
        func_matches = re.findall(r"\b(?:def|class|function|funksiya|metod|method)\s+([a-zA-Z_][a-zA-Z0-9_]*)", prompt, re.IGNORECASE)
        paren_matches = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", prompt)
        combined_syms = list(dict.fromkeys(func_matches + paren_matches))

        skip_words = {
            "print", "len", "str", "int", "dict", "list", "set", "tuple", "if", "for", "while",
            "add", "create", "make", "write", "run", "test", "check", "fix", "update", "delete",
            "yeni", "fayl", "yarat", "yaz", "əlavə", "elave", "et", "işlət", "islet",
        }
        for fn in combined_syms:
            if fn.lower() not in skip_words and len(fn) > 1:
                target_f = file_matches[0] if file_matches else "main.py"
                symbol_reqs.append(SymbolRequirement(
                    path=target_f,
                    symbol_name=fn,
                    symbol_type="any",
                ))

        # 3. Detect test requirements (multi-lingual)
        test_keywords = ["test", "pytest", "unittest", "jest", "vitest", "yaz test", "testı işlət", "testləri", "проверь", "тест"]
        if any(k in p_lower for k in test_keywords):
            test_target = file_matches[0] if file_matches else None
            test_reqs.append(TestRequirement(
                require_tests_executed=True,
                target_path=test_target,
            ))

        # 4. Content behavior patterns if strings specified (e.g., returning "Goodbye " + name)
        str_quotes = re.findall(r'["\']([^"\']+)["\']', prompt)
        for sq in str_quotes:
            if len(sq) > 2 and file_matches:
                behavior_reqs.append(BehaviorRequirement(
                    description=f"Content contains string '{sq}'",
                    check_type="contains",
                    pattern_or_code=sq,
                    target_file=file_matches[0],
                ))

        return TaskRequirement(
            prompt=prompt,
            files=file_reqs,
            symbols=symbol_reqs,
            behaviors=behavior_reqs,
            tests=test_reqs,
        )
