"""Plugin: gcp — Google Cloud Platform Compute and Cloud Storage tools."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def gcp_gcs_upload(**kwargs) -> dict:
    """Gcp Gcs Upload execution handler."""
    return {"status": "success", "tool": "gcp_gcs_upload", "args": kwargs}

@vibe_tool
def gcp_run_deploy(**kwargs) -> dict:
    """Gcp Run Deploy execution handler."""
    return {"status": "success", "tool": "gcp_run_deploy", "args": kwargs}

