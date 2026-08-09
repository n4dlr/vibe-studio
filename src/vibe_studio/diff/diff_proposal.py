"""Diff Proposal Manager for Vibe Studio.

Captures file modifications as structured DiffProposals for validation, diff preview,
and explicit user accept/reject/revert actions.
"""
from __future__ import annotations

import difflib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DiffProposal:
    proposal_id: str
    execution_id: str
    file_path: str
    original_content: str
    proposed_content: str
    diff_text: str
    status: str = "pending"  # pending, accepted, rejected, reverted
    timestamp: float = field(default_factory=time.time)


class DiffProposalManager:
    """Manages structured file change proposals before committing edits."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.proposals: Dict[str, DiffProposal] = {}

    def create_proposal(
        self,
        execution_id: str,
        rel_file_path: str,
        proposed_content: str,
    ) -> DiffProposal:
        import uuid
        target = self.workspace_root / rel_file_path
        orig_content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""

        diff_lines = list(
            difflib.unified_diff(
                orig_content.splitlines(keepends=True),
                proposed_content.splitlines(keepends=True),
                fromfile=f"a/{rel_file_path}",
                tofile=f"b/{rel_file_path}",
            )
        )
        diff_text = "".join(diff_lines)
        proposal_id = f"prop_{uuid.uuid4().hex[:8]}"

        prop = DiffProposal(
            proposal_id=proposal_id,
            execution_id=execution_id,
            file_path=rel_file_path,
            original_content=orig_content,
            proposed_content=proposed_content,
            diff_text=diff_text,
        )
        self.proposals[proposal_id] = prop
        return prop

    def accept_proposal(self, proposal_id: str) -> bool:
        prop = self.proposals.get(proposal_id)
        if not prop or prop.status != "pending":
            return False
        target = self.workspace_root / prop.file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(prop.proposed_content, encoding="utf-8")
        prop.status = "accepted"
        return True

    def reject_proposal(self, proposal_id: str) -> bool:
        prop = self.proposals.get(proposal_id)
        if not prop or prop.status != "pending":
            return False
        prop.status = "rejected"
        return True

    def revert_proposal(self, proposal_id: str) -> bool:
        prop = self.proposals.get(proposal_id)
        if not prop or prop.status != "accepted":
            return False
        target = self.workspace_root / prop.file_path
        if prop.original_content == "":
            if target.exists():
                target.unlink()
        else:
            target.write_text(prop.original_content, encoding="utf-8")
        prop.status = "reverted"
        return True
