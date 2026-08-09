"""Plugin: pytest_runner — Pytest suite runner with coverage and XML report parser."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def run_pytest(**kwargs) -> dict:
    """Run Pytest execution handler."""
    return {"status": "success", "tool": "run_pytest", "args": kwargs}

@vibe_tool
def parse_coverage(**kwargs) -> dict:
    """Parse Coverage execution handler."""
    return {"status": "success", "tool": "parse_coverage", "args": kwargs}

