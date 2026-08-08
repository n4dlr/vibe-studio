from __future__ import annotations

from pathlib import Path

from vibe_studio.tools.filesystem_tools import FilesystemTools
from vibe_studio.tools.patch_tools import PatchTools
from vibe_studio.tools.search_tools import SearchTools
from vibe_studio.tools.tool_registry import default_tool_registry


def test_filesystem_tools_operations(tmp_path: Path):
    fs = FilesystemTools(tmp_path)
    file1 = "src/demo.py"
    fs.create_file(file1, "print('hello world')\n")
    assert fs.file_exists(file1)
    assert "hello world" in fs.read_file(file1)

    fs.write_file(file1, "print('updated')\n")
    assert "updated" in fs.read_file(file1)

    meta = fs.get_file_metadata(file1)
    assert meta["size"] > 0

    fs.delete_file(file1)
    assert not fs.file_exists(file1)


def test_search_and_patch_tools(tmp_path: Path):
    fs = FilesystemTools(tmp_path)
    search = SearchTools(tmp_path)
    patch = PatchTools(tmp_path)

    file_path = "src/app.py"
    fs.create_file(file_path, "def login():\n    return 'old_bg'\n")

    res = search.search_text("login")
    assert len(res) == 1
    assert res[0]["file"] == file_path

    patch_res = patch.patch_file(file_path, "return 'old_bg'", "return 'new_bg'")
    assert patch_res["status"] == "success"
    assert "new_bg" in fs.read_file(file_path)

    # Test Undo
    assert patch.undo_last_change() is True
    assert "old_bg" in fs.read_file(file_path)


def test_tool_registry_execution(tmp_path: Path):
    reg = default_tool_registry(tmp_path)
    res = reg.execute("create_file", {"path": "test.txt", "content": "123"})
    assert res["exit_code"] == 0

    read_res = reg.execute("read_file", {"path": "test.txt"})
    assert "123" in read_res["stdout"]
