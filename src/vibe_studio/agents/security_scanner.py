"""SecurityScanner — scans project files for hardcoded secrets, SQL injection, and XSS risks."""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SecurityFinding:
    file: str
    line: int
    severity: str
    category: str
    message: str
    snippet: str


class SecurityScanner:
    """Detects security vulnerabilities in project source code."""

    SECRET_PATTERN = re.compile(
        r"(password|secret|api_key|token|auth_token|key)[a_z0-9_]*\s*=\s*['\"]([^'\"]{4,})['\"]",
        re.IGNORECASE,
    )
    SQLI_PATTERN = re.compile(
        r"(execute|query)\s*\(\s*f['\"].*SELECT.*FROM|execute\s*\(\s*['\"].*%\s*s",
        re.IGNORECASE,
    )
    XSS_PATTERN = re.compile(
        r"dangerouslySetInnerHTML|innerHTML\s*=\s*|document\.write\s*\(",
        re.IGNORECASE,
    )

    def scan_file(self, file_path: Path, workspace_root: Path) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        try:
            rel = file_path.relative_to(workspace_root).as_posix()
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return findings

        for idx, line in enumerate(content.splitlines(), start=1):
            line_str = line.strip()

            # Hardcoded credentials check
            m = self.SECRET_PATTERN.search(line_str)
            if m and not line_str.startswith("#") and "os.getenv" not in line_str:
                findings.append(
                    SecurityFinding(
                        file=rel,
                        line=idx,
                        severity="HIGH",
                        category="Hardcoded Secret",
                        message=f"Possible hardcoded credential key '{m.group(1)}'",
                        snippet=line_str,
                    )
                )

            # SQL Injection check
            if self.SQLI_PATTERN.search(line_str):
                findings.append(
                    SecurityFinding(
                        file=rel,
                        line=idx,
                        severity="CRITICAL",
                        category="SQL Injection",
                        message="Possible unsafe SQL query string formatting",
                        snippet=line_str,
                    )
                )

            # XSS check
            if self.XSS_PATTERN.search(line_str):
                findings.append(
                    SecurityFinding(
                        file=rel,
                        line=idx,
                        severity="MEDIUM",
                        category="Cross-Site Scripting (XSS)",
                        message="Direct innerHTML assignment detected",
                        snippet=line_str,
                    )
                )

        return findings

    def scan_project(self, workspace_root: Path) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        for p in workspace_root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in skip for part in p.parts):
                continue
            if p.suffix in {".py", ".js", ".ts", ".jsx", ".tsx", ".html"}:
                findings.extend(self.scan_file(p, workspace_root))
        return findings
