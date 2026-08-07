from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectInfo:
    root: Path
    files: list[str]


class ProjectManager:
    def __init__(self, root: Path | None = None):
        self.root = root

    def open_project(self, root: Path) -> ProjectInfo:
        self.root = root
        files = self._list_all_files(root)
        return ProjectInfo(root=root, files=files)

    def list_files(self) -> list[str]:
        if self.root is None:
            return []
        return self._list_all_files(self.root)

    def _list_all_files(self, root: Path) -> list[str]:
        paths: list[str] = []
        for child in root.rglob("*"):
            if child.is_file():
                relative = child.relative_to(root).as_posix()
                paths.append(relative)
        return sorted(paths)

    def iter_files(self) -> Iterator[Path]:
        if self.root is None:
            return iter(())
        return iter(sorted(p for p in self.root.rglob("*") if p.is_file()))
