from __future__ import annotations

from pathlib import Path

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "secrets.json",
    "credentials",
    "firebase-adminsdk",
}


class SensitiveFileDetector:
    @staticmethod
    def is_sensitive(path: str | Path) -> bool:
        target = str(path).lower()
        file_name = Path(target).name.lower()
        if file_name in SENSITIVE_NAMES:
            return True
        return any(marker in target for marker in [".pem", ".key", ".p12", ".env", "secret", "credential"])

    @staticmethod
    def flag_if_needed(path: str | Path) -> bool:
        return SensitiveFileDetector.is_sensitive(path)
