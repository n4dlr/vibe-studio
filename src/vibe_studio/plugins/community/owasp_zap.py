"""Plugin: owasp_zap — OWASP ZAP dynamic application security testing (DAST)."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def zap_baseline_scan(**kwargs) -> dict:
    """Zap Baseline Scan execution handler."""
    return {"status": "success", "tool": "zap_baseline_scan", "args": kwargs}

@vibe_tool
def zap_spider(**kwargs) -> dict:
    """Zap Spider execution handler."""
    return {"status": "success", "tool": "zap_spider", "args": kwargs}

