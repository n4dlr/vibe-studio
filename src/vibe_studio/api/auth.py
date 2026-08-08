"""API Authentication — verifies API keys for remote REST endpoints."""
from __future__ import annotations

import os


class APIAuth:
    """Validates API token header against VIBE_STUDIO_API_KEY environment variable."""

    @staticmethod
    def verify_key(api_key: str) -> bool:
        expected = os.getenv("VIBE_STUDIO_API_KEY", "")
        if not expected:
            return True  # If no key configured, open access on local loopback
        return api_key == expected
