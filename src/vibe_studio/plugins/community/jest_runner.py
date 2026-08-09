"""Plugin: jest_runner — Jest JavaScript/TypeScript unit test runner."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def run_jest(**kwargs) -> dict:
    """Run Jest execution handler."""
    return {"status": "success", "tool": "run_jest", "args": kwargs}

@vibe_tool
def jest_coverage(**kwargs) -> dict:
    """Jest Coverage execution handler."""
    return {"status": "success", "tool": "jest_coverage", "args": kwargs}

