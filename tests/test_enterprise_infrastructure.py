"""Unit test suite for the 14 enterprise production infrastructure layers."""
import time
import pytest
from pathlib import Path

from vibe_studio.agents.coding_agent import AgentState
from vibe_studio.core.cancellation import CancellationToken
from vibe_studio.core.resource_manager import ResourceManager
from vibe_studio.core.checkpoint_system import CheckpointSystem, StateTransitionValidator
from vibe_studio.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from vibe_studio.core.retry_manager import RetryManager
from vibe_studio.core.cache_manager import CacheManager
from vibe_studio.security.input_sanitizer import InputSanitizer
from vibe_studio.security.audit_logger import AuditLogger


# ── 1. Resource Manager & Lifecycle ──────────────────────────────────────────

def test_resource_manager_cleanup():
    rm = ResourceManager()
    exec_id = "test_exec_123"
    rm._record_allocation(exec_id, "test_res")
    assert rm.get_active_count(exec_id) == 1
    rm.cleanup_execution(exec_id)
    assert rm.get_active_count(exec_id) == 0


# ── 2. Checkpoint System & State Transition Validator ────────────────────────

def test_state_transition_validator():
    # Valid transition
    assert StateTransitionValidator.validate_transition(AgentState.IDLE, AgentState.EXECUTING) is True
    # Invalid transition (CANCELLED -> EXECUTING is invalid)
    assert StateTransitionValidator.validate_transition(AgentState.CANCELLED, AgentState.EXECUTING) is False

    with pytest.raises(ValueError):
        StateTransitionValidator.enforce_transition(AgentState.CANCELLED, AgentState.EXECUTING)


def test_checkpoint_system(tmp_path):
    cs = CheckpointSystem(tmp_path, max_checkpoints=3)
    exec_id = "exec_test_abc"

    cs.save_checkpoint(exec_id, 1, AgentState.EXECUTING, "Task 1", ["a.py"])
    cs.save_checkpoint(exec_id, 2, AgentState.OBSERVING, "Task 1", ["a.py", "b.py"])

    latest = cs.get_latest_checkpoint(exec_id)
    assert latest is not None
    assert latest.step_number == 2
    assert latest.state == AgentState.OBSERVING.value


# ── 3. Circuit Breaker ────────────────────────────────────────────────────────

def test_circuit_breaker_tripping():
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout=1.0)

    def failing_fn():
        raise RuntimeError("API Error")

    with pytest.raises(RuntimeError):
        cb.call(failing_fn)

    with pytest.raises(RuntimeError):
        cb.call(failing_fn)

    # Circuit should now be OPEN
    with pytest.raises(CircuitBreakerOpenException):
        cb.call(failing_fn)


# ── 4. Retry Manager ─────────────────────────────────────────────────────────

def test_retry_manager_success_after_retry():
    attempts = 0

    def flaky_fn():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Temporary failure")
        return "success"

    rm = RetryManager(max_retries=3, base_delay=0.01)
    result = rm.execute(flaky_fn)
    assert result == "success"
    assert attempts == 2


# ── 5. Cache Manager ──────────────────────────────────────────────────────────

def test_cache_manager_ttl():
    cache = CacheManager(default_ttl_seconds=0.1)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"

    time.sleep(0.15)
    assert cache.get("key1") is None


# ── 6. Input Sanitizer & Audit Logger ───────────────────────────────────────

def test_input_sanitizer_blocks_dangerous_patterns(tmp_path):
    with pytest.raises(ValueError, match="Dangerous command pattern"):
        InputSanitizer.sanitize_command("rm -rf /")

    with pytest.raises(ValueError, match="Path traversal blocked"):
        InputSanitizer.sanitize_path("../../etc/passwd", tmp_path)


def test_audit_logger(tmp_path):
    logger = AuditLogger(log_dir=tmp_path)
    logger.log_action("tool_execute", "exec_101", tool_name="read_file", target_path="/home/user/test.py")
    assert (tmp_path / "audit.jsonl").exists()
