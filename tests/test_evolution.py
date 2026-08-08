"""
Comprehensive unit test suite for Vibe Studio Evolution modules across Phase 1, Phase 2, and Phase 3.
"""
from __future__ import annotations

import os
os.environ.setdefault("VIBE_STUDIO_OFFLINE", "1")

import json
from pathlib import Path
import pytest

from vibe_studio.providers.offline_provider import OfflineFallbackProvider
from vibe_studio.core.thread_manager import ThreadManager
from vibe_studio.terminal.shell_detector import ShellDetector
from vibe_studio.context.learning_engine import LearningEngine
from vibe_studio.agents.intent_predictor import IntentPredictor
from vibe_studio.agents.security_scanner import SecurityScanner
from vibe_studio.agents.performance_analyzer import PerformanceAnalyzer
from vibe_studio.agents.dependency_checker import DependencyChecker
from vibe_studio.agents.proactive_analyzer import ProactiveAnalyzer
from vibe_studio.agents.self_learning_tests import SelfLearningTests
from vibe_studio.core.message_bus import MessageBus, AgentMessage
from vibe_studio.agents.navigator_agent import NavigatorAgent
from vibe_studio.agents.reviewer_agent import ReviewerAgent
from vibe_studio.agents.debug_assistant import DebugAssistant
from vibe_studio.plugin.plugin_manager import PluginManager
from vibe_studio.api.auth import APIAuth
from vibe_studio.api.server import APIServerHandler
from vibe_studio.cloud.sync_manager import SyncManager


class TestEvolutionPhase1:
    def test_offline_fallback_provider(self):
        provider = OfflineFallbackProvider()
        assert provider.test_connection()
        models = provider.list_models()
        assert len(models) == 1
        assert models[0].name == "offline-deterministic"
        res = provider.generate(prompt="hello", model="offline-deterministic")
        assert "Offline mode active" in res

    def test_shell_detector(self):
        name, cmd = ShellDetector.detect_shell()
        assert name in ("cmd", "PowerShell", "bash", "zsh", "sh")
        formatted = ShellDetector.format_command("echo 1")
        assert len(formatted) >= 2


class TestEvolutionPhase2:
    def test_learning_engine(self, tmp_path):
        engine = LearningEngine(tmp_path)
        engine.record_event("file_open", {"file": "main.py"})
        engine.record_event("file_open", {"file": "main.py"})
        engine.record_event("file_open", {"file": "utils.py"})

        frequent = engine.get_frequently_accessed_files()
        assert frequent[0] == "main.py"

    def test_intent_predictor(self):
        predictor = IntentPredictor()
        predictor.record_command("npm install")
        suggestions = predictor.predict_next("npm install")
        assert "npm start" in suggestions

    def test_security_scanner(self, tmp_path):
        scanner = SecurityScanner()
        vuln_file = tmp_path / "vulnerable.py"
        vuln_file.write_text('secret_key = "1234567890"\nquery = f"SELECT * FROM users WHERE id = {user_id}"\n', encoding="utf-8")

        findings = scanner.scan_project(tmp_path)
        assert len(findings) >= 1
        cats = [f.category for f in findings]
        assert "Hardcoded Secret" in cats or "SQL Injection" in cats

    def test_performance_analyzer(self, tmp_path):
        analyzer = PerformanceAnalyzer()
        perf_file = tmp_path / "perf.py"
        perf_file.write_text("for i in range(10):\n    for j in range(10):\n        print(i, j)\n", encoding="utf-8")

        findings = analyzer.scan_project(tmp_path)
        assert len(findings) >= 1
        assert "O(n²)" in findings[0].message

    def test_dependency_checker(self, tmp_path):
        checker = DependencyChecker()
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests\npytest==8.0.0\n", encoding="utf-8")

        findings = checker.scan_project(tmp_path)
        assert len(findings) == 1
        assert findings[0].package == "requests"

    def test_self_learning_tests(self, tmp_path):
        slt = SelfLearningTests()
        code_file = tmp_path / "math_utils.py"
        code_file.write_text("def compute_factorial(n):\n    return 1\n", encoding="utf-8")

        untested = slt.find_untested_functions(tmp_path)
        assert len(untested) == 1
        assert untested[0].function_name == "compute_factorial"

        tmpl = slt.generate_test_template(untested[0])
        assert "test_compute_factorial" in tmpl

    def test_message_bus(self):
        bus = MessageBus()
        received = []

        def _sub(msg: AgentMessage):
            received.append(msg)

        bus.subscribe("task_done", _sub)
        bus.publish(AgentMessage(sender="Coder", topic="task_done", payload={"status": "ok"}))

        assert len(received) == 1
        assert received[0].sender == "Coder"

    def test_navigator_agent(self, tmp_path):
        nav = NavigatorAgent(tmp_path)
        m_file = tmp_path / "main.py"
        m_file.write_text("def main(): pass\n", encoding="utf-8")

        files = nav.discover_relevant_files("main")
        assert "main.py" in files

    def test_reviewer_agent(self):
        reviewer = ReviewerAgent()
        diff = "+ print('debug log')\n+ except:\n+     pass\n"
        res = reviewer.review_diff(diff)
        assert len(res.feedback) >= 1
        assert res.score < 100

    def test_debug_assistant(self):
        assistant = DebugAssistant()
        tb = 'File "src/app.py", line 42, in run\n    val = 1 / 0\nZeroDivisionError: division by zero'
        analysis = assistant.analyze_traceback(tb)
        assert analysis.error_type == "ZeroDivisionError"
        assert analysis.line_number == 42
        assert len(analysis.suggestions) == 3


class TestEvolutionPhase3:
    def test_plugin_manager(self, tmp_path):
        plugin_dir = tmp_path / "plugins"
        pm = PluginManager(plugin_dir)

        p_file = plugin_dir / "sample_plugin.py"
        p_file.write_text('def register_tools(): return {"sample_tool": lambda: "hello"}\n', encoding="utf-8")

        discovered = pm.discover_plugins()
        assert "sample_plugin.py" in discovered

        loaded = pm.load_plugin("sample_plugin.py", tmp_path)
        assert loaded
        assert "sample_tool" in pm.registered_tools
        assert pm.registered_tools["sample_tool"]() == "hello"

    def test_api_auth_and_server(self, tmp_path):
        handler = APIServerHandler(tmp_path)
        res = handler.handle_analyze()
        assert "languages" in res
        assert "total_files" in res

    def test_sync_manager(self, tmp_path):
        sync = SyncManager(tmp_path)
        sync.memory.record_modification("main.py", "edit", "Updated main function")

        bundle = sync.export_sync_bundle()
        assert "main.py" in bundle

        imported = sync.import_sync_bundle(bundle)
        assert imported
