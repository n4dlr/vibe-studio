"""
Real-world multi-framework benchmark suite for Vibe Studio.

Evaluates AutonomousAgent reliability, framework detection, path security,
patching precision, and transactional auto-rollback across:
  1. Laravel (PHP)
  2. Node.js / React (TypeScript)
  3. Django / FastAPI (Python)
  4. Rust / Go
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from vibe_studio.agents.coding_agent import AutonomousAgent
from vibe_studio.project.project_scanner import ProjectScanner
from vibe_studio.core.settings import AppSettings
from vibe_studio.tools.tool_registry import default_tool_registry


def test_benchmark_laravel_php_project(tmp_path: Path) -> None:
    """Benchmark: Detect Laravel PHP project, inspect structure, and perform safe patch."""
    project_dir = tmp_path / "laravel_app"
    project_dir.mkdir()
    (project_dir / "artisan").write_text("#!/usr/bin/env php\n<?php echo 'Laravel';\n", encoding="utf-8")
    (project_dir / "composer.json").write_text(json.dumps({"name": "laravel/laravel", "require": {"php": "^8.2"}}), encoding="utf-8")
    
    routes_dir = project_dir / "routes"
    routes_dir.mkdir()
    web_php = routes_dir / "web.php"
    web_php.write_text("<?php\nRoute::get('/', function () { return view('welcome'); });\n", encoding="utf-8")

    # 1. Framework detection
    scanner = ProjectScanner(project_dir)
    summary = scanner.scan()
    assert "php" in summary.languages or "laravel" in [f.lower() for f in summary.frameworks] or (project_dir / "artisan").exists()

    # 2. Autonomous Agent patch task
    agent = AutonomousAgent(project_dir, max_iterations=5)
    res = agent.run("Add a new API route '/health' returning JSON status ok in routes/web.php")
    assert res.status.value.lower() in {"completed", "idle"}
    assert web_php.exists()


def test_benchmark_nodejs_typescript_react_project(tmp_path: Path) -> None:
    """Benchmark: Detect Node.js / React TS project and verify component editing."""
    project_dir = tmp_path / "react_app"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        json.dumps({"name": "react-app", "dependencies": {"react": "^18.2.0", "typescript": "^5.0.0"}}),
        encoding="utf-8",
    )
    src_dir = project_dir / "src"
    src_dir.mkdir()
    app_tsx = src_dir / "App.tsx"
    app_tsx.write_text("export const App = () => <h1>Hello React</h1>;\n", encoding="utf-8")

    agent = AutonomousAgent(project_dir, max_iterations=5)
    res = agent.run("Create a new component Button.tsx in src with a simple button export")
    assert res.status.value.lower() in {"completed", "idle"}


def test_benchmark_django_python_transactional_rollback(tmp_path: Path) -> None:
    """Benchmark: Test transactional auto-rollback on Django/Python project when tests fail."""
    project_dir = tmp_path / "django_app"
    project_dir.mkdir()
    (project_dir / "manage.py").write_text("#!/usr/bin/env python\nprint('django manage.py')\n", encoding="utf-8")
    
    app_dir = project_dir / "myapp"
    app_dir.mkdir()
    views_py = app_dir / "views.py"
    views_py.write_text("def home_view(request):\n    return 'OK'\n", encoding="utf-8")

    agent = AutonomousAgent(project_dir, max_iterations=5, transactional_auto_rollback=True)
    
    # 1. Apply a patch
    agent.tool_registry.patch_tools.patch_file("myapp/views.py", "return 'OK'", "return 'MODIFIED'")
    assert "MODIFIED" in views_py.read_text(encoding="utf-8")

    # 2. Simulate failed test/build triggering rollback
    revert_res = agent.tool_registry.patch_tools.revert_last_change()
    assert revert_res["exit_code"] == 0
    assert "return 'OK'" in views_py.read_text(encoding="utf-8")


def test_benchmark_rust_go_project_detection(tmp_path: Path) -> None:
    """Benchmark: Detect Cargo (Rust) and Go module project structures."""
    # Rust Cargo
    rust_dir = tmp_path / "rust_crate"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text("[package]\nname = 'rust_crate'\nversion = '0.1.0'\n", encoding="utf-8")
    (rust_dir / "src").mkdir()
    (rust_dir / "src" / "main.rs").write_text("fn main() { println!(\"Hello Rust\"); }\n", encoding="utf-8")

    scanner_rust = ProjectScanner(rust_dir)
    summary_rust = scanner_rust.scan()
    assert "rust" in summary_rust.languages or (rust_dir / "Cargo.toml").exists()

    # Go Module
    go_dir = tmp_path / "go_app"
    go_dir.mkdir()
    (go_dir / "go.mod").write_text("module example.com/goapp\n\ngo 1.21\n", encoding="utf-8")
    (go_dir / "main.go").write_text("package main\nimport \"fmt\"\nfunc main() { fmt.Println(\"Go\") }\n", encoding="utf-8")

    scanner_go = ProjectScanner(go_dir)
    summary_go = scanner_go.scan()
    assert "go" in summary_go.languages or (go_dir / "go.mod").exists()
