from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentPlan:
    task: str
    steps: list[str] = field(default_factory=list)
    approval_required: bool = True


class CodingAgent:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def analyze(self, task: str) -> AgentPlan:
        return AgentPlan(
            task=task,
            steps=[
                "Inspect the project structure and locate likely files",
                "Rank relevant files and dependencies by task need",
                "Create a minimal, safe patch after approval",
                "Run focused validation and summarize the outcome",
            ],
            approval_required=True,
        )

    def execute(self, task: str) -> dict[str, Any]:
        return {
            "status": "planned",
            "task": task,
            "summary": "The agent analyzed the task and prepared a safe execution plan.",
            "files": [],
        }
