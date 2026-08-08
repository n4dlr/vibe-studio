from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from vibe_studio.app.main_window import MainWindow
from vibe_studio.core.settings import AppSettings, ProviderConfig, SettingsStore


def test_main_window_sends_chat_message(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(
        project_path=str(tmp_path),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(settings_store=store, settings=settings)
    window.chat_input.setPlainText("hello from test")
    window._send_chat_message()
    result = window.chat.toPlainText()
    assert "hello from test" in result
    assert "AI:" in result or "You:" in result


def test_open_project_builds_file_tree_and_opens_file(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    code_file = project_dir / "src" / "main.py"
    code_file.parent.mkdir()
    code_file.write_text("print('hello')\n", encoding="utf-8")

    settings = AppSettings(
        project_path=str(project_dir),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(settings_store=store, settings=settings)

    window.open_project(project_dir)

    assert hasattr(window.explorer, "model")
    assert window.explorer.model().rootPath() == str(project_dir)

    window.open_editor(code_file)
    assert window.editor_tabs.count() == 1
    editor_widget = window.editor_tabs.widget(0)
    assert "print('hello')" in editor_widget.toPlainText()


def test_search_panel_finds_project_text(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    project_dir = tmp_path / "project"
    (project_dir / "src").mkdir(parents=True)
    code_file = project_dir / "src" / "main.py"
    code_file.write_text("print('hello search')\n", encoding="utf-8")

    settings = AppSettings(
        project_path=str(project_dir),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(settings_store=store, settings=settings)

    window.search_panel.set_workspace_root(project_dir)
    window.search_panel.search_input.setText("search")
    window.search_panel._run_search()

    assert window.search_panel.results.count() > 0
    assert "src/main.py" in window.search_panel.results.item(0).text()


def test_chat_service_creates_file_when_prompt_requests_it(tmp_path) -> None:
    settings = AppSettings(
        project_path=str(tmp_path),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    manager = type("DummyManager", (), {"settings": settings, "_get_ollama_url": lambda self: "http://127.0.0.1:11434"})()
    service = __import__("vibe_studio.ai.chat_service", fromlist=["ChatService"]).ChatService(manager)

    result = service.chat("Create a new file src/demo.py with this content:\n```python\nprint('hello from agent')\n```")

    file_path = tmp_path / "src" / "demo.py"
    assert file_path.exists()
    assert "print('hello from agent')" in file_path.read_text(encoding="utf-8")


def test_chat_service_creates_number_file_from_natural_language(tmp_path) -> None:
    settings = AppSettings(
        project_path=str(tmp_path),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    manager = type("DummyManager", (), {"settings": settings, "_get_ollama_url": lambda self: "http://127.0.0.1:11434"})()
    service = __import__("vibe_studio.ai.chat_service", fromlist=["ChatService"]).ChatService(manager)

    service.chat("Create a file with the numbers 1 to 20, one number per line.")

    file_path = tmp_path / "numbers.txt"
    assert file_path.exists()
    lines = file_path.read_text(encoding="utf-8").splitlines()
    assert lines == [str(i) for i in range(1, 21)]


def test_chat_service_deletes_file_when_prompt_requests_it(tmp_path) -> None:
    settings = AppSettings(
        project_path=str(tmp_path),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    manager = type("DummyManager", (), {"settings": settings, "_get_ollama_url": lambda self: "http://127.0.0.1:11434"})()
    service = __import__("vibe_studio.ai.chat_service", fromlist=["ChatService"]).ChatService(manager)

    file_path = tmp_path / "numbers.txt"
    file_path.write_text("1\n2\n3\n", encoding="utf-8")

    result = service.chat("Delete numbers.txt file")

    assert not file_path.exists()


def test_chat_service_deletes_turkish_file_request(tmp_path) -> None:
    settings = AppSettings(
        project_path=str(tmp_path),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    manager = type("DummyManager", (), {"settings": settings, "_get_ollama_url": lambda self: "http://127.0.0.1:11434"})()
    service = __import__("vibe_studio.ai.chat_service", fromlist=["ChatService"]).ChatService(manager)

    file_path = tmp_path / "numbers.txt"
    file_path.write_text("1\n2\n3\n", encoding="utf-8")

    result = service.chat("numbers.txt faylini sil")

    assert not file_path.exists()


def test_chat_service_can_undo_last_edit(tmp_path) -> None:
    settings = AppSettings(
        project_path=str(tmp_path),
        default_provider="ollama",
        default_model="llama3.1",
        providers=[ProviderConfig(name="ollama", kind="ollama", base_url="http://127.0.0.1:11434", model="llama3.1")],
    )
    manager = type("DummyManager", (), {"settings": settings, "_get_ollama_url": lambda self: "http://127.0.0.1:11434"})()
    service = __import__("vibe_studio.ai.chat_service", fromlist=["ChatService"]).ChatService(manager)

    file_path = tmp_path / "notes.txt"
    file_path.write_text("before\n", encoding="utf-8")
    service.chat("Create a file with the numbers 1 to 20, one number per line.")

    num_path = tmp_path / "numbers.txt"
    assert num_path.exists()
    assert service.revert_last_change() is True
    assert not num_path.exists()
