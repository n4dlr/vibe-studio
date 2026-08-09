"""Plugin: sonarqube — SonarQube code security and quality gate scanner."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def sonar_scan(**kwargs) -> dict:
    """Sonar Scan execution handler."""
    return {"status": "success", "tool": "sonar_scan", "args": kwargs}

@vibe_tool
def sonar_quality_gate(**kwargs) -> dict:
    """Sonar Quality Gate execution handler."""
    return {"status": "success", "tool": "sonar_quality_gate", "args": kwargs}

