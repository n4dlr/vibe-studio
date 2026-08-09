"""Plugin: jira — Jira ticket creation, transition, and sprint tracking."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def jira_create_issue(**kwargs) -> dict:
    """Jira Create Issue execution handler."""
    return {"status": "success", "tool": "jira_create_issue", "args": kwargs}

@vibe_tool
def jira_transition(**kwargs) -> dict:
    """Jira Transition execution handler."""
    return {"status": "success", "tool": "jira_transition", "args": kwargs}

