from __future__ import annotations

from pathlib import Path
import pytest

from vibe_studio.security.path_security import PathSecurity, PathSecurityError


def test_path_normalization_and_validation(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    inside = ws / "src" / "main.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("print('hello')", encoding="utf-8")

    res = PathSecurity.validate_workspace_path(inside, ws)
    assert res == inside.resolve()

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(PathSecurityError):
        PathSecurity.validate_workspace_path(outside, ws)

    with pytest.raises(PathSecurityError):
        PathSecurity.validate_workspace_path(ws / ".." / "outside.txt", ws)
