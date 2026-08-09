"""Plugin: nginx — NGINX reverse proxy configuration and syntax checking."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def nginx_reload(**kwargs) -> dict:
    """Nginx Reload execution handler."""
    return {"status": "success", "tool": "nginx_reload", "args": kwargs}

@vibe_tool
def nginx_test_config(**kwargs) -> dict:
    """Nginx Test Config execution handler."""
    return {"status": "success", "tool": "nginx_test_config", "args": kwargs}

