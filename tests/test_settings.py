from __future__ import annotations

from pathlib import Path

from vibe_studio.core.project_memory import ProjectMemory
from vibe_studio.core.settings import AppSettings, ProviderConfig, SettingsStore


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings(
        default_provider="ollama",
        providers=[
            ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")
        ],
    )

    store = SettingsStore(path)
    store.save(settings)
    loaded = store.load()

    assert loaded.default_provider == "ollama"
    assert loaded.providers[0].name == "ollama"
    assert loaded.providers[0].model == "llama3.1"


def test_default_settings_include_ollama() -> None:
    store = SettingsStore(Path("/tmp/test_vibe_settings.json"))
    settings = store.load()
    assert settings.providers[0].kind == "ollama"


def test_project_memory_persists_recent_modifications(tmp_path: Path) -> None:
    memory = ProjectMemory(tmp_path)
    memory.record_modification("src/login.py", "write_file", "Updated login styling")
    memory.record_modification("src/styles.css", "write_file", "Added gradient")

    reloaded = memory.load()
    recent = reloaded["recent_modifications"]
    assert len(recent) == 2
    assert recent[-1]["file"] == "src/styles.css"
