"""Plugin: github — GitHub PR creation, issue management, and workflow dispatch."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def gh_create_pr(**kwargs) -> dict:
    """Gh Create Pr execution handler."""
    return {"status": "success", "tool": "gh_create_pr", "args": kwargs}

@vibe_tool
def gh_list_issues(**kwargs) -> dict:
    """Gh List Issues execution handler."""
    return {"status": "success", "tool": "gh_list_issues", "args": kwargs}

