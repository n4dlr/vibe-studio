"""Benchmark scenarios matrix for VibeBench.

Contains real-world multi-language task scenarios across Python, Node/React, Go, Rust, C++, and Laravel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BenchmarkScenario:
    id: str
    title: str
    language: str
    framework: str
    difficulty: str  # easy, medium, hard
    prompt: str
    expected_files: List[str]
    verification_cmd: str
    initial_files: dict[str, str] = field(default_factory=dict)


BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    # ── Python / FastAPI ──────────────────────────────────────────────────────
    BenchmarkScenario(
        id="py_fastapi_auth",
        title="Python FastAPI Token Auth Route",
        language="python",
        framework="fastapi",
        difficulty="medium",
        prompt="Add a `/login` POST route to `main.py` that validates credentials and returns a JWT token.",
        expected_files=["main.py"],
        verification_cmd="python3 -m unittest test_main.py",
        initial_files={
            "main.py": (
                "from fastapi import FastAPI, HTTPException\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/')\n"
                "def index():\n"
                "    return {'status': 'ok'}\n"
            ),
            "test_main.py": (
                "import unittest\n"
                "from main import app\n\n"
                "class TestAuth(unittest.TestCase):\n"
                "    def test_index(self):\n"
                "        self.assertTrue(hasattr(app, 'routes'))\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            ),
        },
    ),
    # ── Python / Django ───────────────────────────────────────────────────────
    BenchmarkScenario(
        id="py_django_model",
        title="Python Django Model & Migration Fix",
        language="python",
        framework="django",
        difficulty="easy",
        prompt="Add a `created_at` DateTimeField with `auto_now_add=True` to the `UserProfile` model in `models.py`.",
        expected_files=["models.py"],
        verification_cmd="python3 -c 'import models; print(hasattr(models.UserProfile, \"created_at\"))'",
        initial_files={
            "models.py": (
                "class UserProfile:\n"
                "    username: str = ''\n"
                "    email: str = ''\n"
            ),
        },
    ),
    # ── JS / Node / Express ───────────────────────────────────────────────────
    BenchmarkScenario(
        id="node_express_rate_limit",
        title="Node.js Express Rate Limiter",
        language="javascript",
        framework="express",
        difficulty="medium",
        prompt="Create an Express rate limiter middleware in `middleware.js` that limits requests per IP.",
        expected_files=["middleware.js"],
        verification_cmd="node -e 'const m = require(\"./middleware\"); if (!m.rateLimiter) process.exit(1);'",
        initial_files={
            "middleware.js": (
                "function rateLimiter(req, res, next) {\n"
                "    next();\n"
                "}\n"
                "module.exports = { rateLimiter };\n"
            ),
        },
    ),
    # ── TypeScript / React ─────────────────────────────────────────────────────
    BenchmarkScenario(
        id="ts_react_button",
        title="React TypeScript Button Component",
        language="typescript",
        framework="react",
        difficulty="easy",
        prompt="Add a `variant` prop ('primary' | 'secondary') to the `Button` component in `Button.tsx`.",
        expected_files=["Button.tsx"],
        verification_cmd="node -e 'const fs = require(\"fs\"); const c = fs.readFileSync(\"Button.tsx\", \"utf8\"); if (!c.includes(\"variant\")) process.exit(1);'",
        initial_files={
            "Button.tsx": (
                "import React from 'react';\n"
                "interface ButtonProps {\n"
                "    label: string;\n"
                "    onClick: () => void;\n"
                "}\n"
                "export const Button: React.FC<ButtonProps> = ({ label, onClick }) => (\n"
                "    <button onClick={onClick}>{label}</button>\n"
                ");\n"
            ),
        },
    ),
    # ── Go / HTTP Server ──────────────────────────────────────────────────────
    BenchmarkScenario(
        id="go_http_health",
        title="Go HTTP Health Handler",
        language="go",
        framework="standard",
        difficulty="easy",
        prompt="Add a `/healthz` HTTP handler in `main.go` returning JSON `{\"status\": \"healthy\"}`.",
        expected_files=["main.go"],
        verification_cmd="python3 -c 'content = open(\"main.go\").read(); assert \"/healthz\" in content'",
        initial_files={
            "main.go": (
                "package main\n"
                "import \"net/http\"\n"
                "func main() {\n"
                "    http.ListenAndServe(\":8080\", nil)\n"
                "}\n"
            ),
        },
    ),
    # ── Rust / Serde Struct ───────────────────────────────────────────────────
    BenchmarkScenario(
        id="rust_serde_config",
        title="Rust App Config Struct with Default",
        language="rust",
        framework="standard",
        difficulty="medium",
        prompt="Implement `Default` for `AppConfig` in `config.rs` with port 8080 and debug false.",
        expected_files=["config.rs"],
        verification_cmd="python3 -c 'content = open(\"config.rs\").read(); assert \"Default\" in content'",
        initial_files={
            "config.rs": (
                "#[derive(Debug, Clone)]\n"
                "pub struct AppConfig {\n"
                "    pub port: u16,\n"
                "    pub debug: bool,\n"
                "}\n"
            ),
        },
    ),
    # ── PHP / Laravel ─────────────────────────────────────────────────────────
    BenchmarkScenario(
        id="php_laravel_controller",
        title="Laravel User Controller API",
        language="php",
        framework="laravel",
        difficulty="medium",
        prompt="Add an `index` method to `UserController.php` returning JSON response.",
        expected_files=["UserController.php"],
        verification_cmd="python3 -c 'content = open(\"UserController.php\").read(); assert \"function index\" in content'",
        initial_files={
            "UserController.php": (
                "<?php\n"
                "namespace App\\Http\\Controllers;\n"
                "class UserController {\n"
                "}\n"
            ),
        },
    ),
]
