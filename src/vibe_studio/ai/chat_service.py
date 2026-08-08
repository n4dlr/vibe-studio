from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from vibe_studio.ai.model_manager import ModelManager


class ChatService:
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self._history: list[tuple[str, str, str | None]] = []

    def send_system_message(self, message: str) -> str:
        return f"System: {message}"

    def _remember_snapshot(self, file_path: Path, content: str | None) -> None:
        if file_path.exists():
            self._history.append((str(file_path), file_path.read_text(encoding="utf-8", errors="replace"), None))
        elif content is not None:
            self._history.append((str(file_path), "", None))

    def revert_last_change(self) -> bool:
        if not self._history:
            return False
        file_path_str, previous_content, _ = self._history.pop()
        file_path = Path(file_path_str)
        if previous_content == "" and file_path.exists():
            file_path.unlink(missing_ok=True)
            return True
        if file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(previous_content, encoding="utf-8")
        return True

    def _infer_content(self, prompt: str) -> str:
        code_block = re.search(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)```", prompt, re.DOTALL | re.IGNORECASE)
        if code_block:
            return code_block.group(1).strip()

        direct_match = re.search(r"(?:with|and)\s+(?:this\s+)?(?:content|code|text)\s*[:\-]?\s*(.*)$", prompt, re.IGNORECASE | re.DOTALL)
        if direct_match and direct_match.group(1).strip():
            return direct_match.group(1).strip()

        if re.search(r"numbers?\s+1\s*[-–to]+\s*20|1\s*[-–]\s*20|1\s*to\s*20", prompt, re.IGNORECASE):
            return "\n".join(str(i) for i in range(1, 21))

        if re.search(r"(create|make|add)\s+(?:a\s+)?(?:new\s+)?file", prompt, re.IGNORECASE):
            if "1 to 20" in prompt.lower() or "1-20" in prompt.lower() or "1 to twenty" in prompt.lower():
                return "\n".join(str(i) for i in range(1, 21))

        return ""

    def _classify_action(self, prompt: str) -> str:
        lowered = prompt.lower()
        create_markers = [
            "create", "make", "add", "generate", "write", "yaz", "oluştur", "olustur", "ekle",
            "yarat", "new file", "yeni dosya",
        ]
        update_markers = [
            "update", "modify", "edit", "append", "change", "güncelle", "guncelle", "duzenle",
            "değiştir", "degistir", "yenile",
        ]
        delete_markers = [
            "delete", "remove", "trash", "rm", "sil", "sile", "kaldır", "kaldir",
        ]

        if any(marker in lowered for marker in delete_markers):
            return "delete"
        if any(marker in lowered for marker in update_markers):
            return "update"
        if any(marker in lowered for marker in create_markers):
            return "create"
        return "unknown"

    def _default_filename_for_prompt(self, prompt: str) -> str:
        lowered = prompt.lower()
        if re.search(r"(?:numbers?|numaralar?)\s*(?:1\s*[-–to]+\s*20|1\s*[-–]\s*20|1\s*to\s*20|1\s*ile\s*20)", lowered):
            return "numbers.txt"
        if re.search(r"(?:todo|task|yapilacak|gorev|plan)", lowered):
            return "todo.txt"
        if re.search(r"(?:readme|read me|project summary|proje ozeti|projeyi anlat)", lowered):
            return "README.md"
        if re.search(r"(?:notes?|notlar?|journal|gunluk)", lowered):
            return "notes.txt"
        if re.search(r"(?:config|settings|ayarlar|settings file)", lowered):
            return "settings.json"
        return "notes.txt"

    def _infer_target_path(self, prompt: str, root: Path) -> Path | None:
        lowered = prompt.lower()

        explicit = re.search(
            r"(?:create|make|add|update|modify|edit|append|delete|remove|trash|rm|sil|sile|kaldir|guncelle|duzenle|ekle|olustur|yaz|yarat)\s+(?:a\s+)?(?:new\s+)?(?:the\s+)?(?:file\s+)?([A-Za-z0-9_./\\-]+)",
            prompt,
            re.IGNORECASE,
        )
        if explicit:
            candidate = explicit.group(1).strip().strip("`\"'")
            candidate_lower = candidate.lower()
            if candidate_lower not in {"with", "and", "the", "this", "that", "using", "for", "from", "to", "ve", "ile", "için", "bu", "şu", "fayl", "dosya", "folder", "klasor", "dizin"} and (
                "." in candidate or "/" in candidate or "\\" in candidate or "_" in candidate or "-" in candidate or candidate_lower not in {"file", "folder", "fayl", "dosya", "klasor", "dizin"}
            ):
                return (root / candidate).resolve()

        file_name = re.search(r"([A-Za-z0-9_./\\-]+\.(?:txt|md|py|json|yaml|yml|csv|log|html|css|js|ts|java|c|cpp|rs|go))", prompt, re.IGNORECASE)
        if file_name:
            return (root / file_name.group(1).strip().strip("`\"'")).resolve()

        if re.search(r"(?:fayl|dosya|file)\b", lowered):
            return (root / self._default_filename_for_prompt(prompt)).resolve()

        return None

    def _apply_project_edit(self, prompt: str) -> str | None:
        root = Path(self.model_manager.settings.project_path) if self.model_manager.settings.project_path else Path.cwd()
        if not root.exists():
            return None

        content = self._infer_content(prompt)
        target_path = self._infer_target_path(prompt, root)
        if target_path is None:
            return None

        action = self._classify_action(prompt)

        if action == "delete":
            if target_path.exists():
                self._remember_snapshot(target_path, "")
                target_path.unlink()
                return f"Deleted file: {target_path.relative_to(root)}"
            return f"File not found: {target_path.relative_to(root)}"

        if action == "create":
            self._remember_snapshot(target_path, content)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            final_content = (content or "")
            if final_content and not final_content.endswith("\n"):
                final_content += "\n"
            target_path.write_text(final_content, encoding="utf-8")
            return f"Created file: {target_path.relative_to(root)}"

        if action == "update":
            if target_path.exists():
                self._remember_snapshot(target_path, None)
                new_content = content or target_path.read_text(encoding="utf-8", errors="replace")
                if new_content and not new_content.endswith("\n"):
                    new_content += "\n"
                target_path.write_text(new_content, encoding="utf-8")
                return f"Updated file: {target_path.relative_to(root)}"

        return None

    def chat(self, prompt: str) -> str:
        project_edit = self._apply_project_edit(prompt)
        if project_edit:
            return project_edit

        provider = self.model_manager.settings.default_provider
        model = self.model_manager.settings.default_model
        if not model and provider == "ollama":
            model = "llama3.1"
        if not model:
            model = "gpt-4o-mini"

        if provider == "ollama":
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2},
                }
                request = Request(
                    f"{self.model_manager._ollama_url()}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "No response from model.")
            except Exception as exc:
                return f"Ollama unavailable: {exc}"

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
        if api_key:
            base_url = "https://api.openai.com/v1"
            try:
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 1024,
                    "stream": False,
                }
                request = Request(
                    f"{base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                with urlopen(request, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "No response from API provider.")
                return "No response from API provider."
            except Exception as exc:
                return f"API provider unavailable: {exc}"

        return "AI not available. Configure Ollama or set OPENAI_API_KEY/CUSTOM_API_KEY."
