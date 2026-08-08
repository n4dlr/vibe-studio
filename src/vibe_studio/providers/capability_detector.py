"""
Provider capability detection.

Determines whether a model supports:
  - Native tool calling (OpenAI-style function_call / tools parameter)
  - Structured JSON output (json_mode)
  - Streaming
  - Large context windows

Used by the agent to choose the right protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelCapabilities:
    model_name: str
    native_tool_calling: bool = False
    json_mode: bool = False
    streaming: bool = True
    context_window: int = 8192
    notes: str = ""


# Known-good native tool-calling models
_NATIVE_TOOL_MODELS: set[str] = {
    # OpenAI
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
    # Anthropic (via OpenAI-compatible proxy)
    "claude-3-5-sonnet-20241022", "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
    "claude-3-5-haiku",
    # Mistral
    "mistral-large", "mistral-medium", "mistral-small", "mixtral-8x22b",
    # Google (via OpenAI-compatible proxy)
    "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash",
    # Ollama models known to support tool calling
    "qwen2.5-coder", "qwen2.5", "qwen3", "llama3.1", "llama3.2",
    "mistral", "mistral-nemo", "command-r-plus", "firefunction-v2",
}

# Model context windows (approximate)
_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4-turbo": 128000,
    "gpt-4": 8192, "gpt-3.5-turbo": 16385,
    "claude-3-5-sonnet-20241022": 200000, "claude-3-opus": 200000,
    "claude-3-haiku": 200000, "claude-3-5-haiku": 200000,
    "gemini-1.5-pro": 1000000, "gemini-1.5-flash": 1000000,
    "qwen3:8b": 32768, "qwen3:14b": 32768, "qwen2.5-coder:7b": 32768,
    "qwen2.5-coder:14b": 32768, "deepseek-coder-v2:lite": 16384,
    "llama3.1": 131072, "llama3.2": 131072, "mistral": 32768,
    "gemma3:4b": 8192, "gemma3:12b": 16384,
}


def detect_capabilities(model_name: str) -> ModelCapabilities:
    """Return capability profile for a model name."""
    lower = model_name.lower()

    # Check native tool calling
    native_tools = any(
        known in lower
        for known in [n.lower() for n in _NATIVE_TOOL_MODELS]
    )

    # Context window
    ctx = 8192
    for m_name, window in _CONTEXT_WINDOWS.items():
        if m_name.lower() in lower or lower.startswith(m_name.lower()):
            ctx = window
            break

    # JSON mode — most modern models support it
    json_mode = any(
        k in lower for k in ["gpt-4", "gpt-3.5", "claude", "gemini", "qwen", "mistral"]
    )

    notes = ""
    if not native_tools:
        notes = "Using compatibility tool-call protocol (JSON in system prompt)"

    return ModelCapabilities(
        model_name=model_name,
        native_tool_calling=native_tools,
        json_mode=json_mode,
        streaming=True,
        context_window=ctx,
        notes=notes,
    )


def adapt_context_to_model(token_budget: int, capabilities: ModelCapabilities) -> int:
    """
    Return a safe token budget that won't exceed the model's context window.
    Reserves 4096 tokens for the system prompt + tool definitions.
    """
    available = max(1000, capabilities.context_window - 4096)
    return min(token_budget, available)
