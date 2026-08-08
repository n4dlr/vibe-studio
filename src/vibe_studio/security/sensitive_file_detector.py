from __future__ import annotations

import re
from pathlib import Path

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_ed25519",
    "secrets.json",
    "credentials",
    "credentials.json",
    "firebase-adminsdk",
}

SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token|password|auth|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.\:\/]{8,})['\"]?",
    r"sk-[A-Za-z0-9]{20,}",
    r"ghp_[A-Za-z0-9]{30,}",
    r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PRIVATE) KEY-----",
]


class SensitiveFileDetector:
    @staticmethod
    def is_sensitive(path: str | Path) -> bool:
        target = str(path).lower()
        file_name = Path(target).name.lower()
        if file_name in SENSITIVE_NAMES:
            return True
        if file_name.startswith(".env") or file_name.endswith((".pem", ".key", ".p12", ".pkcs12")):
            return True
        if any(marker in file_name for marker in ["id_rsa", "id_ed25519", "credentials.json", "firebase-adminsdk"]):
            return True
        return False

    @staticmethod
    def flag_if_needed(path: str | Path) -> bool:
        return SensitiveFileDetector.is_sensitive(path)

    @staticmethod
    def redact_secrets(text: str) -> str:
        """Scan text and replace sensitive tokens, credentials, and keys with [REDACTED_SECRET]."""
        redacted = text
        for pattern in SECRET_PATTERNS:
            def _replace(match):
                full = match.group(0)
                if len(match.groups()) > 1 and match.group(2):
                    secret_val = match.group(2)
                    return full.replace(secret_val, "[REDACTED_SECRET]")
                return "[REDACTED_SECRET]"
            redacted = re.sub(pattern, _replace, redacted)
        return redacted
