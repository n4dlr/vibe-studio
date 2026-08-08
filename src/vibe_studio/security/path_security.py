from __future__ import annotations

import os
from pathlib import Path


class PathSecurityError(PermissionError):
    """Raised when a path violates security or workspace boundaries."""
    pass


class PathSecurity:
    """Provides path normalization, validation, and workspace boundary enforcement."""

    @staticmethod
    def normalize_path(path: str | Path) -> Path:
        """Resolve absolute path, removing relative components and resolving symlinks where possible."""
        p = Path(path)
        if not p.is_absolute():
            p = p.absolute()
        try:
            return p.resolve()
        except Exception:
            return p

    @staticmethod
    def validate_workspace_path(path: str | Path, workspace_root: str | Path) -> Path:
        """
        Validate that target path resides strictly inside workspace_root.
        Handles relative paths by resolving them relative to workspace_root.
        Prevents path traversal ('../'), symlink escapes, UNC paths, and drive escapes.
        """
        ws_root = PathSecurity.normalize_path(workspace_root)
        p = Path(path)
        if not p.is_absolute():
            target = PathSecurity.normalize_path(ws_root / p)
        else:
            target = PathSecurity.normalize_path(p)

        # Check if target is equal to or relative to workspace root
        try:
            target.relative_to(ws_root)
        except ValueError:
            raise PathSecurityError(
                f"Access denied: path '{target}' is outside allowed workspace '{ws_root}'"
            )

        return target

    @staticmethod
    def is_within_workspace(path: str | Path, workspace_root: str | Path) -> bool:
        """Return True if path is inside workspace_root, False otherwise."""
        try:
            PathSecurity.validate_workspace_path(path, workspace_root)
            return True
        except PathSecurityError:
            return False
