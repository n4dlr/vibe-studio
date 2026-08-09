"""Plugin: grpc — gRPC proto linting and client call tester."""
from vibe_studio.plugin.plugin_api import vibe_tool

@vibe_tool
def grpc_call(**kwargs) -> dict:
    """Grpc Call execution handler."""
    return {"status": "success", "tool": "grpc_call", "args": kwargs}

@vibe_tool
def grpc_proto_compile(**kwargs) -> dict:
    """Grpc Proto Compile execution handler."""
    return {"status": "success", "tool": "grpc_proto_compile", "args": kwargs}

