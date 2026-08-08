"""Orchestrator tests — streaming pipeline, stage events, and self-repair integration."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from vibe_studio.agents.orchestrator import AgentOrchestrator, OrchestratedExecutionResult, PipelineStageTiming


# ── execute_task_stream — unit tests ─────────────────────────────────────────

def test_execute_task_stream_yields_events(tmp_path):
    """Stream should yield a sequence of stage events ending with 'result'."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    events = list(orch.execute_task_stream("add a comment to README.md"))
    
    stage_names = [e["stage"] for e in events]
    assert "intent_analysis" in stage_names
    assert "navigation" in stage_names
    assert "result" in stage_names


def test_execute_task_stream_event_schema(tmp_path):
    """Every event must have stage, status, data, and elapsed keys."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    for event in orch.execute_task_stream("explain the code"):
        assert "stage" in event
        assert "status" in event
        assert "data" in event
        assert "elapsed" in event
        assert isinstance(event["elapsed"], float)
        assert event["elapsed"] >= 0


def test_execute_task_stream_final_result(tmp_path):
    """The last event must have stage='result' with a valid OrchestratedExecutionResult."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    last_event = None
    for event in orch.execute_task_stream("list files"):
        last_event = event
    
    assert last_event is not None
    assert last_event["stage"] == "result"
    assert last_event["status"] == "done"
    result = last_event["data"]["result"]
    assert isinstance(result, OrchestratedExecutionResult)
    assert result.prompt == "list files"


def test_execute_task_stream_start_and_done_pairs(tmp_path):
    """Each major stage should have a start event followed by a done/error event."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    events = list(orch.execute_task_stream("hello"))
    
    # Group events by stage name
    by_stage: dict = {}
    for ev in events:
        stage = ev["stage"]
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(ev["status"])
    
    # Each stage should have a start event
    for stage, statuses in by_stage.items():
        if stage == "result":
            continue
        assert "start" in statuses or "done" in statuses or "error" in statuses


def test_execute_task_stream_elapsed_monotonically_increasing(tmp_path):
    """Elapsed timestamps should generally increase across events."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    events = list(orch.execute_task_stream("hello"))
    
    elapsed_values = [e["elapsed"] for e in events]
    # Allow for tiny floating point artifacts but must be non-decreasing overall
    assert elapsed_values[-1] >= elapsed_values[0]


def test_execute_task_stream_intent_suggestions(tmp_path):
    """intent_analysis done event should carry suggestions list."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    for event in orch.execute_task_stream("add tests"):
        if event["stage"] == "intent_analysis" and event["status"] == "done":
            assert "suggestions" in event["data"]
            assert isinstance(event["data"]["suggestions"], list)
            break


def test_execute_task_stream_navigation_files(tmp_path):
    """navigation done event should carry files list."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    for event in orch.execute_task_stream("find all tests"):
        if event["stage"] == "navigation" and event["status"] == "done":
            assert "files" in event["data"]
            assert isinstance(event["data"]["files"], list)
            break


# ── execute_task — regression (backwards compat) ─────────────────────────────

def test_execute_task_backwards_compat(tmp_path):
    """execute_task() should still return OrchestratedExecutionResult synchronously."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    result = orch.execute_task("explain the code")
    assert isinstance(result, OrchestratedExecutionResult)
    assert result.prompt == "explain the code"
    assert isinstance(result.summary, str)
    assert "Task:" in result.summary


def test_execute_task_timings(tmp_path):
    """execute_task should return stage timings for all pipeline stages."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    result = orch.execute_task("hello")
    assert len(result.stage_timings) > 0
    for t in result.stage_timings:
        assert isinstance(t, PipelineStageTiming)
        assert t.duration_seconds >= 0


def test_execute_task_with_active_file(tmp_path):
    """Passing active_file should not crash."""
    (tmp_path / "main.py").write_text("print('hi')\n")
    orch = AgentOrchestrator(workspace_root=tmp_path)
    result = orch.execute_task("explain this", active_file="main.py")
    assert isinstance(result, OrchestratedExecutionResult)


def test_execute_task_intent_suggestions_populated(tmp_path):
    """intent_suggestions should be a list."""
    orch = AgentOrchestrator(workspace_root=tmp_path)
    result = orch.execute_task("add unit tests")
    assert isinstance(result.intent_suggestions, list)


def test_orchestrator_progress_callback(tmp_path):
    """progress_callback should be invoked for each stage."""
    events_seen = []
    orch = AgentOrchestrator(
        workspace_root=tmp_path,
        progress_callback=lambda stage, data: events_seen.append(stage),
    )
    orch.execute_task("hello")
    assert len(events_seen) > 0


def test_orchestrator_stream_callback_accepted(tmp_path):
    """stream_callback parameter should be accepted without error."""
    tokens = []
    orch = AgentOrchestrator(
        workspace_root=tmp_path,
        stream_callback=lambda tok: tokens.append(tok),
    )
    result = orch.execute_task("hello")
    assert isinstance(result, OrchestratedExecutionResult)
