from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


@dataclass
class FileChangeSnapshot:
    path: str
    previous_content: str
    new_content: str
    diff: str
    hash_before: str
    hash_after: str


class FuzzyPatchEngine:
    """Intelligent fuzzy matching and auto-indentation engine.

    Ensures patches succeed even with minor whitespace drift, line-ending mismatches,
    or subtle indentation differences introduced by LLMs.
    """

    @staticmethod
    def detect_indentation(text: str) -> str:
        """Detect the predominant indentation prefix in the given text."""
        lines = text.splitlines()
        for line in lines:
            if line.startswith("    "):
                return "    "
            if line.startswith("  "):
                return "  "
            if line.startswith("\t"):
                return "\t"
        return "    "

    @staticmethod
    def align_indentation(target_block: str, replacement_block: str) -> str:
        """Adjust replacement_block indentation to match target_block base indentation."""
        target_lines = [l for l in target_block.splitlines() if l.strip()]
        rep_lines = [l for l in replacement_block.splitlines() if l.strip()]
        if not target_lines or not rep_lines:
            return replacement_block

        def get_indent_len(s: str) -> int:
            return len(s) - len(s.lstrip())

        target_base = get_indent_len(target_lines[0])
        rep_base = get_indent_len(rep_lines[0])
        diff = target_base - rep_base

        if diff == 0:
            return replacement_block

        adjusted = []
        for line in replacement_block.splitlines(keepends=True):
            if not line.strip():
                adjusted.append(line)
            elif diff > 0:
                adjusted.append((" " * diff) + line)
            else:
                to_strip = min(-diff, get_indent_len(line))
                adjusted.append(line[to_strip:])
        return "".join(adjusted)

    @classmethod
    def find_best_match(cls, old_content: str, target_text: str) -> tuple[int, int, str] | None:
        """Find the start and end character offsets of the best matching block in old_content.

        Returns: (start_idx, end_idx, matched_string) or None if no match found.
        """
        # 1. Exact match
        idx = old_content.find(target_text)
        if idx != -1:
            return idx, idx + len(target_text), target_text

        # 2. Line-ending normalized match
        t_crlf = target_text.replace("\r\n", "\n").replace("\n", "\r\n")
        t_lf = target_text.replace("\r\n", "\n")
        if t_crlf in old_content:
            idx = old_content.find(t_crlf)
            return idx, idx + len(t_crlf), t_crlf
        if t_lf in old_content:
            idx = old_content.find(t_lf)
            return idx, idx + len(t_lf), t_lf

        # 3. Line-by-line whitespace-stripped match
        content_lines = old_content.splitlines(keepends=True)
        target_lines = target_text.splitlines(keepends=True)
        num_target = len(target_lines)

        if num_target == 0:
            return None

        # Normalized comparison helper
        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", s).strip()

        norm_target_lines = [norm(l) for l in target_lines if norm(l)]
        if not norm_target_lines:
            return None

        # Sliding window over content lines
        best_ratio = 0.0
        best_slice = None

        for window_len in (num_target, max(1, num_target - 1), num_target + 1):
            for i in range(len(content_lines) - window_len + 1):
                window_lines = content_lines[i : i + window_len]
                norm_window_lines = [norm(l) for l in window_lines if norm(l)]

                # Anchor check: first and last normalized line match
                if norm_window_lines and norm_target_lines:
                    if norm_window_lines[0] == norm_target_lines[0] and norm_window_lines[-1] == norm_target_lines[-1]:
                        # High confidence anchor match
                        matcher = difflib.SequenceMatcher(None, norm_target_lines, norm_window_lines)
                        ratio = matcher.ratio()
                        if ratio > best_ratio and ratio >= 0.75:
                            best_ratio = ratio
                            start_char = sum(len(l) for l in content_lines[:i])
                            end_char = start_char + sum(len(l) for l in window_lines)
                            best_slice = (start_char, end_char, "".join(window_lines))

                # General SequenceMatcher
                matcher = difflib.SequenceMatcher(None, norm_target_lines, norm_window_lines)
                ratio = matcher.ratio()
                if ratio > best_ratio and ratio >= 0.85:
                    best_ratio = ratio
                    start_char = sum(len(l) for l in content_lines[:i])
                    end_char = start_char + sum(len(l) for l in window_lines)
                    best_slice = (start_char, end_char, "".join(window_lines))

        return best_slice


class PatchTools:
    """Provides precise and resilient file editing tools with fuzzy matching, AST safety, and undo stack."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)
        self.history: list[FileChangeSnapshot] = []

    def _resolve(self, path: str | Path) -> Path:
        return PathSecurity.validate_workspace_path(path, self.workspace_root)

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    def _diff(self, file_path: str, old_text: str, new_text: str) -> str:
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        return "".join(diff_lines)

    def _create_backup(self, path: str, content: str) -> None:
        try:
            backup_dir = self.workspace_root / ".vibe_studio_backup"
            backup_dir.mkdir(parents=True, exist_ok=True)
            safe_name = path.replace("/", "_").replace("\\", "_")
            backup_file = backup_dir / f"{safe_name}_{self._hash(content)}.bak"
            backup_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def _record_snapshot(self, path: str, old_content: str, new_content: str) -> FileChangeSnapshot:
        diff = self._diff(path, old_content, new_content)
        self._create_backup(path, old_content)
        snapshot = FileChangeSnapshot(
            path=path,
            previous_content=old_content,
            new_content=new_content,
            diff=diff,
            hash_before=self._hash(old_content),
            hash_after=self._hash(new_content),
        )
        self.history.append(snapshot)
        return snapshot

    def check_conflict(self, path: str, expected_hash: str) -> bool:
        """Return True if the file has been modified since expected_hash was recorded."""
        target_path = self._resolve(path)
        if not target_path.exists():
            return False
        current = target_path.read_text(encoding="utf-8", errors="replace")
        return self._hash(current) != expected_hash

    def patch_file(
        self,
        path: str,
        target_text: str | None = None,
        replacement_text: str | None = None,
        *,
        old_text: str | None = None,
        new_text: str | None = None,
    ) -> dict[str, Any]:
        """Apply targeted replacement to a file using resilient fuzzy matching and auto-indentation."""
        if target_text is None:
            target_text = old_text
        if replacement_text is None:
            replacement_text = new_text
        if target_text is None or replacement_text is None:
            return {"exit_code": 1, "stdout": "", "stderr": "target_text and replacement_text are required", "status": "error"}

        target_path = self._resolve(path)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        old_content = target_path.read_text(encoding="utf-8", errors="replace")

        # Find best matching block via FuzzyPatchEngine
        match_result = FuzzyPatchEngine.find_best_match(old_content, target_text)

        if not match_result:
            stripped_target = " ".join(target_text.split())
            stripped_content = " ".join(old_content.split())
            hint = "(found with whitespace differences)" if stripped_target in stripped_content else ""
            raise ValueError(
                f"Target text not found in '{path}'. {hint}\n"
                "Tip: use read_file to check the current exact content before patching."
            )

        start_idx, end_idx, matched_str = match_result

        # Auto-align replacement indentation if target was indented
        aligned_replacement = FuzzyPatchEngine.align_indentation(matched_str, replacement_text)

        new_content = old_content[:start_idx] + aligned_replacement + old_content[end_idx:]

        target_path.write_text(new_content, encoding="utf-8")
        rel_path = target_path.relative_to(self.workspace_root).as_posix()
        snapshot = self._record_snapshot(rel_path, old_content, new_content)

        return {
            "exit_code": 0,
            "status": "success",
            "file": rel_path,
            "stdout": f"Patched {rel_path}",
            "stderr": "",
            "diff": snapshot.diff,
            "hash_before": snapshot.hash_before,
            "hash_after": snapshot.hash_after,
        }

    def replace_text(self, path: str, old_str: str, new_str: str) -> dict[str, Any]:
        return self.patch_file(path, old_str, new_str)

    def insert_text(self, path: str, position_text: str, text_to_insert: str, after: bool = True) -> dict[str, Any]:
        """Insert text before or after position_text with fuzzy anchor support."""
        target_path = self._resolve(path)
        old_content = target_path.read_text(encoding="utf-8", errors="replace") if target_path.exists() else ""

        if not position_text:
            new_content = old_content + "\n" + text_to_insert if old_content else text_to_insert
        else:
            match_res = FuzzyPatchEngine.find_best_match(old_content, position_text)
            if not match_res:
                raise ValueError(f"Position text '{position_text[:40]}' not found in {path}")
            start_idx, end_idx, matched_pos = match_res
            if after:
                new_content = old_content[:end_idx] + "\n" + text_to_insert + old_content[end_idx:]
            else:
                new_content = old_content[:start_idx] + text_to_insert + "\n" + old_content[start_idx:]

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_content, encoding="utf-8")
        rel_path = target_path.relative_to(self.workspace_root).as_posix()
        snapshot = self._record_snapshot(rel_path, old_content, new_content)

        return {
            "status": "success",
            "file": rel_path,
            "diff": snapshot.diff,
        }

    def delete_text(self, path: str, text_to_delete: str) -> dict[str, Any]:
        return self.patch_file(path, text_to_delete, "")

    def structured_patch(self, path: str, patches: list[dict[str, str]]) -> dict[str, Any]:
        """Apply a sequence of atomic patches to a file."""
        target_path = self._resolve(path)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        old_content = target_path.read_text(encoding="utf-8", errors="replace")
        current_content = old_content

        for patch in patches:
            target = patch.get("target", "")
            replacement = patch.get("replacement", "")
            match_res = FuzzyPatchEngine.find_best_match(current_content, target)
            if not match_res:
                raise ValueError(f"Target block '{target[:30]}...' not found in {path}")
            start_idx, end_idx, matched_str = match_res
            aligned_rep = FuzzyPatchEngine.align_indentation(matched_str, replacement)
            current_content = current_content[:start_idx] + aligned_rep + current_content[end_idx:]

        target_path.write_text(current_content, encoding="utf-8")
        rel_path = target_path.relative_to(self.workspace_root).as_posix()
        snapshot = self._record_snapshot(rel_path, old_content, current_content)

        return {
            "status": "success",
            "file": rel_path,
            "patches_applied": len(patches),
            "diff": snapshot.diff,
        }

    def undo_last_change(self) -> bool:
        """Revert the most recent file change and return boolean success."""
        if not self.history:
            return False
        last_snap = self.history.pop()
        target_path = self._resolve(last_snap.path)
        if last_snap.previous_content == "":
            target_path.unlink(missing_ok=True)
        else:
            target_path.write_text(last_snap.previous_content, encoding="utf-8")
        return True

    def undo_last_patch(self) -> dict[str, Any]:
        """Revert the most recent file change and return detailed dict."""
        if not self.history:
            return {"exit_code": 1, "status": "error", "message": "No patches to undo."}
        last_snap = self.history.pop()
        target_path = self._resolve(last_snap.path)
        if last_snap.previous_content == "":
            target_path.unlink(missing_ok=True)
        else:
            target_path.write_text(last_snap.previous_content, encoding="utf-8")
        return {
            "exit_code": 0,
            "status": "success",
            "file": last_snap.path,
            "stdout": f"Successfully reverted changes to {last_snap.path}",
            "message": f"Successfully reverted changes to {last_snap.path}",
        }

    def revert_last_change(self) -> dict[str, Any]:
        """Alias for undo_last_patch returning detailed dict."""
        return self.undo_last_patch()

    def revert_file_change(self, path: str) -> dict[str, Any]:
        """Revert the most recent patch specifically targeting the given file."""
        norm_path = Path(path).as_posix()
        for i in range(len(self.history) - 1, -1, -1):
            snap = self.history[i]
            if snap.path == norm_path or snap.path.endswith(norm_path) or norm_path.endswith(snap.path):
                self.history.pop(i)
                target_path = self._resolve(snap.path)
                if snap.previous_content == "":
                    target_path.unlink(missing_ok=True)
                else:
                    target_path.write_text(snap.previous_content, encoding="utf-8")
                return {
                    "exit_code": 0,
                    "status": "success",
                    "file": snap.path,
                    "stdout": f"Successfully reverted {snap.path}",
                    "message": f"Successfully reverted {snap.path}",
                }
        return {"exit_code": 1, "status": "error", "message": f"No patch history found for {path}."}
