"""State Checkpoint System & State Transition Validator for Vibe Studio.

Provides N-step rolling execution checkpoints for crash recovery and strict state transition validation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class StateTransitionValidator:
    """Validates allowable agent state machine transitions."""

    # Set of valid target states from each source state (using string values)
    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        "IDLE": {"ANALYZING", "PLANNING", "EXECUTING"},
        "ANALYZING": {"PLANNING", "FAILED", "CANCELLED"},
        "PLANNING": {"WAITING_APPROVAL", "EXECUTING", "FAILED", "CANCELLED"},
        "WAITING_APPROVAL": {"EXECUTING", "CANCELLED", "FAILED"},
        "EXECUTING": {"OBSERVING", "VALIDATING", "FIXING", "REVIEWING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "PARTIAL", "FAILED", "CANCELLED", "BLOCKED"},
        "OBSERVING": {"EXECUTING", "VALIDATING", "FIXING", "REVIEWING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "PARTIAL", "FAILED", "CANCELLED", "BLOCKED"},
        "VALIDATING": {"FIXING", "REVIEWING", "COMPLETED", "COMPLETED_WITH_WARNINGS", "PARTIAL", "FAILED", "CANCELLED", "BLOCKED"},
        "FIXING": {"EXECUTING", "FAILED", "CANCELLED", "BLOCKED"},
        "REVIEWING": {"COMPLETED", "COMPLETED_WITH_WARNINGS", "PARTIAL", "FAILED", "CANCELLED", "BLOCKED"},
        "COMPLETED": {"IDLE"},
        "COMPLETED_WITH_WARNINGS": {"IDLE"},
        "PARTIAL": {"IDLE"},
        "FAILED": {"IDLE"},
        "CANCELLED": {"IDLE"},
        "BLOCKED": {"IDLE", "FAILED", "CANCELLED"},
    }

    @classmethod
    def validate_transition(cls, current_state: Any, target_state: Any) -> bool:
        """Return True if the state transition is valid, False otherwise."""
        curr_val = current_state.value if hasattr(current_state, "value") else str(current_state)
        tgt_val = target_state.value if hasattr(target_state, "value") else str(target_state)

        if curr_val == tgt_val:
            return True
        allowed = cls.ALLOWED_TRANSITIONS.get(curr_val, set())
        return tgt_val in allowed

    @classmethod
    def enforce_transition(cls, current_state: Any, target_state: Any) -> None:
        """Raise ValueError if the transition is invalid."""
        if not cls.validate_transition(current_state, target_state):
            curr_val = current_state.value if hasattr(current_state, "value") else str(current_state)
            tgt_val = target_state.value if hasattr(target_state, "value") else str(target_state)
            raise ValueError(f"Invalid state transition: {curr_val} -> {tgt_val}")


@dataclass
class Checkpoint:
    checkpoint_id: str
    execution_id: str
    step_number: int
    state: str
    task: str
    files_changed: List[str]
    context_summary: str = ""
    timestamp: float = 0.0


class CheckpointSystem:
    """Manages rolling execution checkpoints on disk."""

    def __init__(self, workspace_root: Path, max_checkpoints: int = 5):
        self.workspace_root = Path(workspace_root)
        self.checkpoint_dir = self.workspace_root / ".vibe_studio" / "checkpoints"
        self.max_checkpoints = max_checkpoints
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        execution_id: str,
        step_number: int,
        state: AgentState,
        task: str,
        files_changed: List[str],
        context_summary: str = "",
    ) -> Checkpoint:
        """Save a new execution checkpoint and maintain maximum rolling count."""
        import time

        cp_id = f"cp_{execution_id[:8]}_step{step_number}_{int(time.time())}"
        cp = Checkpoint(
            checkpoint_id=cp_id,
            execution_id=execution_id,
            step_number=step_number,
            state=state.value,
            task=task,
            files_changed=files_changed,
            context_summary=context_summary,
            timestamp=time.time(),
        )

        cp_file = self.checkpoint_dir / f"{cp_id}.json"
        try:
            cp_file.write_text(json.dumps(asdict(cp), indent=2), encoding="utf-8")
        except Exception:
            pass

        self._prune_old_checkpoints(execution_id)
        return cp

    def get_latest_checkpoint(self, execution_id: str) -> Optional[Checkpoint]:
        """Load the latest checkpoint for an execution ID."""
        cps = self.list_checkpoints(execution_id)
        return cps[-1] if cps else None

    def list_checkpoints(self, execution_id: str) -> List[Checkpoint]:
        """List all checkpoints sorted by timestamp."""
        checkpoints: List[Checkpoint] = []
        for file in self.checkpoint_dir.glob(f"cp_{execution_id[:8]}_*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                checkpoints.append(Checkpoint(**data))
            except Exception:
                pass
        checkpoints.sort(key=lambda c: c.timestamp)
        return checkpoints

    def _prune_old_checkpoints(self, execution_id: str) -> None:
        cps = self.list_checkpoints(execution_id)
        if len(cps) > self.max_checkpoints:
            to_remove = cps[: len(cps) - self.max_checkpoints]
            for cp in to_remove:
                file = self.checkpoint_dir / f"{cp.checkpoint_id}.json"
                if file.exists():
                    try:
                        file.unlink()
                    except Exception:
                        pass
