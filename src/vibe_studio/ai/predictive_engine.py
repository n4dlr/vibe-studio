"""Predictive Coding Engine — Proactively predicts developer's next logical actions."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from vibe_studio.ai.suggestion_cache import SuggestionCache
from vibe_studio.core.global_memory import GlobalMemory

logger = logging.getLogger(__name__)


class PredictiveCodingEngine:
    """Predictive coding assistant that analyzes document context to recommend next steps."""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.memory = GlobalMemory()
        self.cache = SuggestionCache(capacity=50, ttl_seconds=30.0)

    def predict_next_actions(
        self,
        current_file: Optional[str] = None,
        cursor_line: int = 1,
        file_content: str = "",
        recent_edits: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Predicts high-probability next developer actions based on current editor state."""
        cache_key = f"{current_file}:{cursor_line}:{hash(file_content[:500])}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        suggestions: List[Dict[str, Any]] = []

        # 1. Structural file type analysis
        if current_file:
            fname = Path(current_file).name.lower()
            if fname.endswith("test.py") or fname.startswith("test_"):
                suggestions.append({
                    "action": "run_tests",
                    "title": "Run Test Suite",
                    "description": f"Execute tests in {fname}",
                    "confidence": 0.92,
                })
                suggestions.append({
                    "action": "add_assertion",
                    "title": "Add Boundary Assertions",
                    "description": "Add exception or edge-case tests",
                    "confidence": 0.85,
                })
            elif fname.endswith(".py"):
                if "def " in file_content and "docstring" not in file_content and '"""' not in file_content:
                    suggestions.append({
                        "action": "add_docstrings",
                        "title": "Add Docstrings & Type Annotations",
                        "description": "Document newly defined functions",
                        "confidence": 0.88,
                    })
                if "import " in file_content:
                    suggestions.append({
                        "action": "refactor_imports",
                        "title": "Clean & Group Imports",
                        "description": "Sort imports according to PEP8",
                        "confidence": 0.79,
                    })
            elif fname == "requirements.txt" or fname == "pyproject.toml":
                suggestions.append({
                    "action": "sync_dependencies",
                    "title": "Audit & Sync Dependencies",
                    "description": "Verify version compatibility",
                    "confidence": 0.95,
                })

        # 2. Historical memory pattern match
        try:
            patterns = self.memory.recall_patterns(file_content[:100] if file_content else "code")
            for p in patterns[:3]:
                solution_text = getattr(p, "solution_summary", "Apply historical fix pattern")
                p_type = getattr(p, "pattern_type", "hint")
                suggestions.append({
                    "action": f"memory_hint:{p_type}",
                    "title": f"Memory Hint: {p_type}",
                    "description": solution_text,
                    "confidence": 0.82,
                })
        except Exception:
            pass

        # Default fallbacks if empty
        if not suggestions:
            suggestions.append({
                "action": "write_unit_test",
                "title": "Generate Unit Tests",
                "description": "Create tests for current module",
                "confidence": 0.75,
            })
            suggestions.append({
                "action": "security_audit",
                "title": "Run Security Scan",
                "description": "Scan file for path traversal & vulnerabilities",
                "confidence": 0.70,
            })

        # Sort by confidence descending
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        self.cache.put(cache_key, suggestions)
        return suggestions
