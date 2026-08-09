from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from vibe_studio.security.path_security import PathSecurity


class FilesystemTools:
    """Implement safe filesystem tools restricted to workspace boundaries."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = PathSecurity.normalize_path(workspace_root)

    def _resolve(self, path: str | Path) -> Path:
        return PathSecurity.validate_workspace_path(path, self.workspace_root)

    def list_directory(self, path: str = ".") -> list[dict[str, Any]]:
        target = self._resolve(path)
        if not target.is_dir():
            raise ValueError(f"'{path}' is not a directory.")

        results = []
        for child in sorted(target.iterdir()):
            rel = child.relative_to(self.workspace_root).as_posix()
            results.append({
                "name": child.name,
                "path": rel,
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else 0,
            })
        return results

    def tree(self, path: str = ".", max_depth: int = 3) -> str:
        target = self._resolve(path)
        lines: list[str] = [target.name + "/"]

        def _build_tree(dir_path: Path, prefix: str = "", depth: int = 1):
            if depth > max_depth:
                return
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for idx, entry in enumerate(entries):
                if entry.name.startswith(".") or entry.name in {"__pycache__", "node_modules", "target", "venv", ".venv", "dist", "build"}:
                    continue
                connector = "└── " if idx == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
                if entry.is_dir():
                    sub_prefix = prefix + ("    " if idx == len(entries) - 1 else "│   ")
                    _build_tree(entry, sub_prefix, depth + 1)

        _build_tree(target)
        return "\n".join(lines)

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        # Check for binary content
        try:
            with open(target, "rb") as f:
                header = f.read(4096)
                if b"\x00" in header:
                    size = target.stat().st_size
                    return f"[Binary file: {target.name} ({size} bytes)]"
        except Exception:
            pass

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        if start_line <= 1 and end_line is None:
            return "".join(lines)

        s_idx = max(0, start_line - 1)
        e_idx = len(lines) if end_line is None else min(len(lines), end_line)
        return "".join(lines[s_idx:e_idx])

    def read_multiple_files(self, paths: list[str]) -> dict[str, str]:
        res = {}
        for p in paths:
            try:
                res[p] = self.read_file(p)
            except Exception as exc:
                res[p] = f"Error reading file: {exc}"
        return res

    def write_file(self, path: str, content: str) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel = target.relative_to(self.workspace_root).as_posix()
        return f"Successfully written to {rel}"

    def create_file(self, path: str, content: str = "") -> str:
        target = self._resolve(path)
        existed = target.exists() and target.stat().st_size > 0
        res = self.write_file(path, content)
        if existed:
            rel = target.relative_to(self.workspace_root).as_posix()
            return f"Updated existing file '{rel}' successfully. (Note: use patch_file for partial edits)"
        return res

    def delete_file(self, path: str) -> str:
        target = self._resolve(path)
        if not target.exists():
            return f"File already removed or does not exist: {path}"
        if target.is_dir():
            shutil.rmtree(target)
            return f"Deleted directory: {path}"
        target.unlink()
        return f"Deleted file: {path}"

    def move_file(self, source: str, destination: str) -> str:
        src = self._resolve(source)
        dst = self._resolve(destination)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {source} to {destination}"

    def copy_file(self, source: str, destination: str) -> str:
        src = self._resolve(source)
        dst = self._resolve(destination)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dst))
        return f"Copied {source} to {destination}"

    def rename_file(self, path: str, new_name: str) -> str:
        target = self._resolve(path)
        dst = target.parent / new_name
        try:
            rel_dst = dst.relative_to(self.workspace_root).as_posix()
        except ValueError:
            rel_dst = str(dst)
        return self.move_file(path, rel_dst)

    def file_exists(self, path: str) -> bool:
        try:
            return self._resolve(path).is_file()
        except Exception:
            return False

    def directory_exists(self, path: str) -> bool:
        try:
            return self._resolve(path).is_dir()
        except Exception:
            return False

    def get_file_metadata(self, path: str) -> dict[str, Any]:
        target = self._resolve(path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        stat = target.stat()
        return {
            "name": target.name,
            "path": target.relative_to(self.workspace_root).as_posix(),
            "size": stat.st_size,
            "is_dir": target.is_dir(),
            "extension": target.suffix,
            "modified": stat.st_mtime,
        }
