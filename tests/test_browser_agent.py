"""Tests for BrowserController (stub mode — no Playwright required)."""
from __future__ import annotations

import pytest
from vibe_studio.agents.browser_agent import (
    BrowserController,
    BrowserResult,
    BROWSER_TOOL_SCHEMAS,
    _PLAYWRIGHT_AVAILABLE,
)


# ---------------------------------------------------------------------------
# Schema tests (always run, no Playwright needed)
# ---------------------------------------------------------------------------

class TestBrowserToolSchemas:
    def test_all_schemas_have_required_fields(self):
        for schema in BROWSER_TOOL_SCHEMAS:
            assert "name" in schema, f"Missing 'name' in {schema}"
            assert "description" in schema
            assert "parameters" in schema
            assert "risk" in schema

    def test_schema_names_are_unique(self):
        names = [s["name"] for s in BROWSER_TOOL_SCHEMAS]
        assert len(names) == len(set(names)), "Duplicate schema names found"

    def test_expected_schemas_present(self):
        names = {s["name"] for s in BROWSER_TOOL_SCHEMAS}
        required = {
            "browser_launch", "browser_navigate", "browser_click",
            "browser_type", "browser_screenshot", "browser_inspect",
            "browser_console_logs", "browser_network_logs",
            "browser_record", "browser_evaluate", "browser_close",
        }
        assert required.issubset(names), f"Missing schemas: {required - names}"

    def test_risk_levels_are_valid(self):
        valid_risks = {"SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
        for schema in BROWSER_TOOL_SCHEMAS:
            assert schema["risk"] in valid_risks, f"{schema['name']} has invalid risk: {schema['risk']}"


# ---------------------------------------------------------------------------
# BrowserResult dataclass
# ---------------------------------------------------------------------------

class TestBrowserResult:
    def test_to_dict_structure(self):
        result = BrowserResult(True, "navigate", data={"url": "http://example.com"}, elapsed_ms=123.4)
        d = result.to_dict()
        assert d["success"] is True
        assert d["action"] == "navigate"
        assert d["data"]["url"] == "http://example.com"
        assert d["elapsed_ms"] == 123.4
        assert "error" in d

    def test_failed_result(self):
        result = BrowserResult(False, "click", error="Element not found")
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "Element not found"

    def test_elapsed_is_rounded(self):
        result = BrowserResult(True, "test", elapsed_ms=12.3456789)
        d = result.to_dict()
        assert d["elapsed_ms"] == 12.3

    def test_default_data_is_empty_dict(self):
        result = BrowserResult(True, "close")
        assert result.data == {}


# ---------------------------------------------------------------------------
# BrowserController stub mode (Playwright not installed)
# ---------------------------------------------------------------------------

class TestBrowserControllerStubMode:
    """These tests verify graceful behaviour when Playwright is absent."""

    def test_instantiation_does_not_raise(self):
        ctrl = BrowserController()
        assert ctrl is not None

    def test_is_not_launched_initially(self):
        ctrl = BrowserController()
        assert ctrl.is_launched() is False

    def test_current_url_before_launch(self):
        ctrl = BrowserController()
        assert ctrl.current_url() == ""

    def test_page_title_before_launch(self):
        ctrl = BrowserController()
        assert ctrl.page_title() == ""

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_launch_returns_error_when_playwright_missing(self):
        ctrl = BrowserController()
        result = ctrl.launch()
        assert result.success is False
        assert "playwright" in result.error.lower() or "not installed" in result.error.lower()

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_navigate_without_launch_returns_error(self):
        ctrl = BrowserController()
        result = ctrl.navigate("http://example.com")
        assert result.success is False

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_click_without_launch_returns_error(self):
        ctrl = BrowserController()
        result = ctrl.click("#btn")
        assert result.success is False

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_screenshot_without_launch_returns_error(self):
        ctrl = BrowserController()
        result = ctrl.screenshot()
        assert result.success is False

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_inspect_without_launch_returns_error(self):
        ctrl = BrowserController()
        result = ctrl.inspect()
        assert result.success is False

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_console_logs_empty_before_launch(self):
        ctrl = BrowserController()
        result = ctrl.console_logs()
        # Should not crash, returns empty or error
        assert isinstance(result, BrowserResult)

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_network_logs_empty_before_launch(self):
        ctrl = BrowserController()
        result = ctrl.network_logs()
        assert isinstance(result, BrowserResult)

    @pytest.mark.skipif(_PLAYWRIGHT_AVAILABLE, reason="Only tests stub mode")
    def test_record_without_launch_returns_error(self):
        ctrl = BrowserController()
        result = ctrl.record("start")
        assert result.success is False

    def test_record_invalid_action(self):
        ctrl = BrowserController()
        result = ctrl.record("dance")
        assert result.success is False
        # May say "Unknown action" or "Playwright not installed" depending on env
        assert result.error

    def test_context_manager_does_not_raise(self):
        with BrowserController() as ctrl:
            pass

    def test_close_without_launch_does_not_raise(self):
        ctrl = BrowserController()
        result = ctrl.close()
        assert isinstance(result, BrowserResult)


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------

class TestBrowserControllerConfig:
    def test_default_config(self):
        ctrl = BrowserController()
        assert ctrl.browser_type == "chromium"
        assert ctrl.headless is True
        assert ctrl.viewport == {"width": 1280, "height": 800}
        assert ctrl.default_timeout == 15_000
        assert ctrl.raise_on_error is False

    def test_custom_config(self):
        ctrl = BrowserController(
            browser_type="firefox",
            headless=False,
            viewport_width=1920,
            viewport_height=1080,
            default_timeout_ms=30_000,
        )
        assert ctrl.browser_type == "firefox"
        assert ctrl.headless is False
        assert ctrl.viewport == {"width": 1920, "height": 1080}
        assert ctrl.default_timeout == 30_000

    def test_screenshots_dir_set(self, tmp_path):
        ctrl = BrowserController(screenshots_dir=tmp_path)
        assert ctrl.screenshots_dir == tmp_path


# ---------------------------------------------------------------------------
# Playwright live tests (only run if Playwright is installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestBrowserControllerLive:
    """Integration tests that require a real Playwright installation."""

    def test_launch_and_close(self):
        ctrl = BrowserController(headless=True)
        result = ctrl.launch()
        assert result.success, result.error
        assert ctrl.is_launched()
        ctrl.close()
        assert not ctrl.is_launched()

    def test_navigate_to_about_blank(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            result = ctrl.navigate("about:blank")
            assert result.success, result.error

    def test_screenshot_returns_base64(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            ctrl.navigate("about:blank")
            result = ctrl.screenshot()
            assert result.success, result.error
            assert result.data["base64"]
            assert result.data["size_bytes"] > 0

    def test_console_logs_capture(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            ctrl.navigate("about:blank")
            ctrl.evaluate("console.log('hello from vibe studio')")
            logs = ctrl.console_logs()
            assert logs.success
            texts = [e["text"] for e in logs.data["entries"]]
            assert any("hello" in t for t in texts)

    def test_network_log_captures_requests(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            ctrl.navigate("https://example.com")
            nw = ctrl.network_logs()
            assert nw.success
            assert nw.data["total"] > 0

    def test_inspect_returns_structure(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            ctrl.navigate("about:blank")
            result = ctrl.inspect()
            assert result.success

    def test_evaluate_returns_value(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            ctrl.navigate("about:blank")
            result = ctrl.evaluate("1 + 1")
            assert result.success
            assert result.data["result"] == 2

    def test_record_start_stop(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            start = ctrl.record("start")
            assert start.success
            ctrl.navigate("about:blank")
            stop = ctrl.record("stop")
            assert stop.success
            assert stop.data["status"] == "stopped"

    def test_page_title_after_navigate(self):
        with BrowserController(headless=True) as ctrl:
            ctrl.launch()
            ctrl.navigate("about:blank")
            title = ctrl.page_title()
            assert isinstance(title, str)
