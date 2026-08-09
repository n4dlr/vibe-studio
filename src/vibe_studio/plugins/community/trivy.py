"""Plugin: trivy — Trivy container image and filesystem vulnerability audit."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def trivy_scan_image(**kwargs) -> dict:
    """Trivy Scan Image execution handler."""
    return {"status": "success", "tool": "trivy_scan_image", "args": kwargs}

@vibe_tool
def trivy_scan_fs(**kwargs) -> dict:
    """Trivy Scan Fs execution handler."""
    return {"status": "success", "tool": "trivy_scan_fs", "args": kwargs}

