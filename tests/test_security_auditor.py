"""Tests for AI Security Auditor."""
from __future__ import annotations

import pytest
from vibe_studio.security.security_auditor import SecurityAuditor


def test_security_auditor_scan(tmp_path):
    vulnerable_file = tmp_path / "vulnerable.py"
    vulnerable_file.write_text(
        "import subprocess\n"
        "AWS_KEY = 'AKIA1234567890ABCDEF'\n"
        "eval('1+1')\n"
        "subprocess.run('ls', shell=True)\n"
    )

    auditor = SecurityAuditor(workspace_root=tmp_path)
    report = auditor.scan_workspace()

    assert report.total_files_scanned >= 1
    assert len(report.findings) >= 3
    assert report.has_high_risk is True
    assert "AI Security Audit Report" in report.to_markdown()
