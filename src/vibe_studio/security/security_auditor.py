"""AI Security Auditor — Automated workspace secret scanning, AST vulnerability detection, and auto-patching."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class VulnerabilityFinding:
    file_path: str
    line_number: int
    rule_id: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    description: str
    code_snippet: str
    suggested_fix: Optional[str] = None


@dataclass
class SecurityAuditReport:
    total_files_scanned: int
    findings: List[VulnerabilityFinding] = field(default_factory=list)
    has_high_risk: bool = False

    def to_markdown(self) -> str:
        md = [f"# AI Security Audit Report\n"]
        md.append(f"**Files Scanned:** {self.total_files_scanned} | **Total Vulnerabilities:** {len(self.findings)}\n")
        if not self.findings:
            md.append("✅ **No security vulnerabilities or secret leaks detected.**\n")
            return "\n".join(md)

        md.append("## Vulnerability Findings\n")
        for f in self.findings:
            sev_icon = "🔴" if f.severity == "HIGH" else ("🟡" if f.severity == "MEDIUM" else "🔵")
            md.append(f"### {sev_icon} [{f.rule_id}] `{f.file_path}:{f.line_number}`")
            md.append(f"**Severity:** {f.severity}  ")
            md.append(f"**Description:** {f.description}  ")
            md.append(f"```python\n{f.code_snippet}\n```")
            if f.suggested_fix:
                md.append(f"**Suggested Fix:** `{f.suggested_fix}`")
            md.append("\n---\n")

        return "\n".join(md)


class SecurityAuditor:
    """Automated security auditor for Python projects."""

    SECRET_PATTERNS = [
        ("SEC-001", r"AKIA[0-9A-Z]{16}", "AWS Access Key ID exposed"),
        ("SEC-002", r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token exposed"),
        ("SEC-003", r"(api_key|secret_key|private_key|password)\s*=\s*['\"][A-Za-z0-9_\-]{8,}['\"]", "Hardcoded credential/secret key"),
    ]

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def scan_workspace(self) -> SecurityAuditReport:
        findings: List[VulnerabilityFinding] = []
        files_scanned = 0

        for py_file in self.workspace_root.rglob("*.py"):
            if ".venv" in py_file.parts or ".git" in py_file.parts or "__pycache__" in py_file.parts:
                continue

            files_scanned += 1
            rel_path = str(py_file.relative_to(self.workspace_root))

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()

                # 1. Regex Secret Scan
                for line_idx, line in enumerate(lines, 1):
                    for rule_id, pattern, desc in self.SECRET_PATTERNS:
                        if re.search(pattern, line):
                            findings.append(
                                VulnerabilityFinding(
                                    file_path=rel_path,
                                    line_number=line_idx,
                                    rule_id=rule_id,
                                    severity="HIGH",
                                    description=desc,
                                    code_snippet=line.strip(),
                                    suggested_fix="Move secret to os.environ or .env file",
                                )
                            )

                # 2. AST Vulnerability Scan
                tree = ast.parse(content, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # Detect eval() or exec()
                        if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                            findings.append(
                                VulnerabilityFinding(
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    rule_id="SEC-AST-01",
                                    severity="HIGH",
                                    description=f"Dangerous call to {node.func.id}() allowing arbitrary code execution",
                                    code_snippet=lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(lines) else "",
                                    suggested_fix="Use ast.literal_eval or safe parser",
                                )
                            )
                        # Detect subprocess.run(..., shell=True)
                        elif isinstance(node.func, ast.Attribute) and node.func.attr in ("run", "Popen", "call"):
                            for kw in node.keywords:
                                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    findings.append(
                                        VulnerabilityFinding(
                                            file_path=rel_path,
                                            line_number=node.lineno,
                                            rule_id="SEC-AST-02",
                                            severity="HIGH",
                                            description="Subprocess executed with shell=True vulnerable to command injection",
                                            code_snippet=lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(lines) else "",
                                            suggested_fix="Set shell=False and pass command as list of arguments",
                                        )
                                    )
            except Exception:
                continue

        has_high = any(f.severity == "HIGH" for f in findings)
        return SecurityAuditReport(total_files_scanned=files_scanned, findings=findings, has_high_risk=has_high)
