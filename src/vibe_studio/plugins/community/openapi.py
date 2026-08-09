"""Plugin: openapi — OpenAPI (Swagger) spec validator and mock server."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def openapi_validate(**kwargs) -> dict:
    """Openapi Validate execution handler."""
    return {"status": "success", "tool": "openapi_validate", "args": kwargs}

@vibe_tool
def openapi_mock(**kwargs) -> dict:
    """Openapi Mock execution handler."""
    return {"status": "success", "tool": "openapi_mock", "args": kwargs}

