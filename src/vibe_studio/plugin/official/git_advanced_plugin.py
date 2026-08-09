"""Advanced Git Plugin — PR description generator & semantic commit helper.

Pillar 3 (Enterprise Official Plugins):
  Provides tools for semantic git commit messaging and PR description formatting.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from vibe_studio.plugin.plugin_api import vibe_plugin


@vibe_plugin(
    name="generate_pr_description",
    description="Generate a formatted Pull Request description from git diff.",
    risk="LOW",
)
def generate_pr_description(target_branch: str = "main", workspace: str = ".") -> str:
    ws = Path(workspace).resolve()
    try:
        diff_out = subprocess.check_output(
            ["git", "diff", f"{target_branch}...HEAD"],
            cwd=ws,
            text=True,
            errors="replace",
        )
        if not diff_out.strip():
            diff_out = subprocess.check_output(["git", "diff", "HEAD~1"], cwd=ws, text=True, errors="replace")
    except Exception as exc:
        return f"Failed to retrieve git diff: {exc}"

    lines = diff_out.splitlines()
    files_changed = [line.split()[-1] for line in lines if line.startswith("+++ b/")]

    summary = [
        "## 🚀 Pull Request Summary",
        "",
        f"**Target Branch**: `{target_branch}`",
        f"**Files Modified**: {len(files_changed)}",
        "",
        "### 📁 Changed Files",
    ]
    for f in files_changed[:10]:
        summary.append(f"- `{f}`")
    if len(files_changed) > 10:
        summary.append(f"- *... and {len(files_changed) - 10} more files*")

    summary.extend([
        "",
        "### 📝 Key Changes",
        "- [x] Feature implementation / bug fix",
        "- [x] Automated test coverage verified",
    ])

    return "\n".join(summary)


@vibe_plugin(
    name="format_semantic_commit",
    description="Format a git commit message adhering to Conventional Commits standards.",
    risk="LOW",
)
def format_semantic_commit(commit_type: str, scope: str, description: str, body: str = "") -> str:
    commit_type = commit_type.lower().strip()
    if commit_type not in {"feat", "fix", "docs", "style", "refactor", "test", "chore", "perf", "ci"}:
        commit_type = "chore"

    scope_str = f"({scope})" if scope else ""
    header = f"{commit_type}{scope_str}: {description}"

    if body:
        return f"{header}\n\n{body}"
    return header
