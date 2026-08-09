"""Plugin: linear — Linear project issue creation and status synchronization."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def linear_create_issue(**kwargs) -> dict:
    """Linear Create Issue execution handler."""
    return {"status": "success", "tool": "linear_create_issue", "args": kwargs}

@vibe_tool
def linear_sync(**kwargs) -> dict:
    """Linear Sync execution handler."""
    return {"status": "success", "tool": "linear_sync", "args": kwargs}

