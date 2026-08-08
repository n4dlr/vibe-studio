from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field
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


class PatchTools:
    """Provides precise targeted file editing tools, snapshot tracking, unified diff generation, and undo stack."""

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
        # Accept old_text/new_text as aliases for compatibility
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

        if target_text not in old_content:
            # Normalize line endings (\r\n vs \n)
            target_crlf = target_text.replace("\r\n", "\n").replace("\n", "\r\n")
            target_lf = target_text.replace("\r\n", "\n")
            if target_crlf in old_content:
                target_text = target_crlf
            elif target_lf in old_content:
                target_text = target_lf
            else:
                # Try normalised whitespace match to give useful feedback
                stripped_target = " ".join(target_text.split())
                stripped_content = " ".join(old_content.split())
                hint = "(found with whitespace differences)" if stripped_target in stripped_content else ""
                raise ValueError(
                    f"Target text not found verbatim in '{path}'. {hint}"
                    "\nTip: use read_file to get the exact current content before patching."
                )

        new_content = old_content.replace(target_text, replacement_text, 1)
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

    def insert_text(self, path: str, position_text: str, text_to_insert: str, after: bool = True) -> dict[str, True]:
        target_path = self._resolve(path)
        old_content = target_path.read_text(encoding="utf-8", errors="replace") if target_path.exists() else ""

        if not position_text:
            new_content = old_content + "\n" + text_to_insert if old_content else text_to_insert
        else:
            if position_text not in old_content:
                pos_crlf = position_text.replace("\r\n", "\n").replace("\n", "\r\n")
                pos_lf = position_text.replace("\r\n", "\n")
                if pos_crlf in old_content:
                    position_text = pos_crlf
                elif pos_lf in old_content:
                    position_text = pos_lf
                else:
                    raise ValueError(f"Position text '{position_text}' not found in {path}")
            if after:
                replacement = position_text + "\n" + text_to_insert
            else:
                replacement = text_to_insert + "\n" + position_text
            new_content = old_content.replace(position_text, replacement, 1)

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
        target_path = self._resolve(path)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        old_content = target_path.read_text(encoding="utf-8", errors="replace")
        current_content = old_content

        for patch in patches:
            target = patch.get("target", "")
            replacement = patch.get("replacement", "")
            if target not in current_content:
                t_crlf = target.replace("\r\n", "\n").replace("\n", "\r\n")
                t_lf = target.replace("\r\n", "\n")
                if t_crlf in current_content:
                    target = t_crlf
                elif t_lf in current_content:
                    target = t_lf
                else:
                    raise ValueError(f"Target block '{target[:30]}...' not found in {path}")
            current_content = current_content.replace(target, replacement, 1)

        target_path.write_text(current_content, encoding="utf-8")
        rel_path = target_path.relative_to(self.workspace_root).as_posix()
        snapshot = self._record_snapshot(rel_path, old_content, current_content)

        return {
            "status": "success",
            "file": rel_path,
            "diff": snapshot.diff,
        }

    def multi_file_patch(self, file_patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for patch in file_patches:
            path = patch.get("file", "")
            target = patch.get("target", "")
            replacement = patch.get("replacement", "")
            res = self.patch_file(path, target, replacement)
            results.append(res)
        return results

    def undo_last_change(self) -> bool:
        if not self.history:
            return False
        snapshot = self.history.pop()
        target_path = self._resolve(snapshot.path)
        if snapshot.previous_content == "" and snapshot.hash_before == self._hash(""):
            if target_path.exists():
                target_path.unlink()
                return True
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(snapshot.previous_content, encoding="utf-8")
        return True

    def revert_last_change(self) -> dict[str, Any]:
        ok = self.undo_last_change()
        return {"exit_code": 0 if ok else 1, "status": "success" if ok else "error", "stdout": "Reverted last change" if ok else "No changes to revert", "stderr": ""}
