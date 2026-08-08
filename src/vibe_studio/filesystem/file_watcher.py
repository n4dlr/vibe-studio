"""WorkspaceFileWatcher — real-time disk file modification watcher for Vibe Studio."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal, Slot


class WorkspaceFileWatcher(QObject):
    """Monitors workspace directory for file changes and emits debounced refresh signals."""

    file_changed = Signal(str)
    directory_changed = Signal(str)

    def __init__(self, workspace_root: str | Path | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.watcher = QFileSystemWatcher(self)
        self.workspace_root: Path | None = None

        self.watcher.fileChanged.connect(self._on_file_changed)
        self.watcher.directoryChanged.connect(self._on_dir_changed)

        # Debounce timer (300ms) to prevent UI spam on bulk file changes
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._emit_debounced)

        self._pending_files: set[str] = set()
        self._pending_dirs: set[str] = set()

        if workspace_root:
            self.set_workspace_root(workspace_root)

    def set_workspace_root(self, root: str | Path) -> None:
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        if self.watcher.files():
            self.watcher.removePaths(self.watcher.files())

        self.workspace_root = Path(root).resolve()
        if not self.workspace_root.exists():
            return

        # Watch root and key source subdirectories
        watch_dirs = [str(self.workspace_root)]
        skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        for p in self.workspace_root.rglob("*"):
            if p.is_dir() and not any(part in skip for part in p.parts):
                watch_dirs.append(str(p))
                if len(watch_dirs) >= 100:
                    break

        self.watcher.addPaths(watch_dirs)

    @Slot(str)
    def _on_file_changed(self, path: str) -> None:
        self._pending_files.add(path)
        self._debounce_timer.start()

    @Slot(str)
    def _on_dir_changed(self, path: str) -> None:
        self._pending_dirs.add(path)
        self._debounce_timer.start()

    def _emit_debounced(self) -> None:
        for f in self._pending_files:
            self.file_changed.emit(f)
        for d in self._pending_dirs:
            self.directory_changed.emit(d)
        self._pending_files.clear()
        self._pending_dirs.clear()
