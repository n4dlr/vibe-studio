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
            target = ws_root / p
        else:
            target = p

        resolved_target = PathSecurity.normalize_path(target)

        # Check if target is equal to or relative to workspace root
        try:
            resolved_target.relative_to(ws_root)
        except ValueError:
            # Case-insensitive drive and path check for Windows
            if os.name == "nt":
                norm_target = os.path.normcase(os.path.abspath(str(resolved_target)))
                norm_root = os.path.normcase(os.path.abspath(str(ws_root)))
                try:
                    if os.path.commonpath([norm_target, norm_root]) == norm_root:
                        return resolved_target
                except ValueError:
                    pass
            raise PathSecurityError(
                f"Access denied: path '{resolved_target}' is outside allowed workspace '{ws_root}'"
            )

        return resolved_target

    @staticmethod
    def is_within_workspace(path: str | Path, workspace_root: str | Path) -> bool:
        """Return True if path is inside workspace_root, False otherwise."""
        try:
            PathSecurity.validate_workspace_path(path, workspace_root)
            return True
        except PathSecurityError:
            return False
