"""Unit test suite for Process Sandbox & Permission Broker."""
import pytest
from pathlib import Path
from vibe_studio.security.permission_broker import PermissionBroker, PermissionDecision
from vibe_studio.security.process_sandbox import ProcessSandbox


def test_permission_broker_boundaries(tmp_path):
    broker = PermissionBroker(workspace_root=tmp_path)

    # Allowed file access inside workspace
    assert broker.authorize_file_access("main.py") == PermissionDecision.ALLOW

    # Blocked file access escaping workspace root
    assert broker.authorize_file_access("../../etc/passwd") == PermissionDecision.DENY

    # Critical command denied
    assert broker.authorize_command("rm -rf /") == PermissionDecision.DENY


def test_process_sandbox_execution(tmp_path):
    code, stdout, stderr = ProcessSandbox.run_sandboxed(
        "echo Hello Sandbox",
        cwd=tmp_path,
        timeout=10,
    )
    assert code == 0
    assert "Hello Sandbox" in stdout
