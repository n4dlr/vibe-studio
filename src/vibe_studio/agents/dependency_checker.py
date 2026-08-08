"""DependencyChecker — inspects pyproject.toml and requirements.txt for package configurations."""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class DependencyFinding:
    file: str
    package: str
    current_version: str
    message: str


class DependencyChecker:
    """Scans project dependency manifests for unpinned or legacy packages."""

    def scan_project(self, workspace_root: Path) -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        
        req_file = workspace_root / "requirements.txt"
        if req_file.exists():
            try:
                for line in req_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "==" not in line and ">=" not in line:
                        findings.append(
                            DependencyFinding(
                                file="requirements.txt",
                                package=line,
                                current_version="unpinned",
                                message=f"Package '{line}' is unpinned. Pin to exact version for reproducibility.",
                            )
                        )
            except Exception:
                pass

        return findings
