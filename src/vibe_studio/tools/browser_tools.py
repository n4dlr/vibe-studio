"""BrowserTools — Bridge between BrowserController and the agent ToolRegistry.

Enables the agent to autonomously browse the web, test web apps, inspect DOM,
capture screenshots, execute JavaScript, and extract structured web content.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from vibe_studio.agents.browser_agent import BrowserController, BrowserResult

logger = logging.getLogger(__name__)


class BrowserTools:
    """Manages browser session lifecycle and exposes tools for the AI agent."""

    def __init__(self, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self._controller: BrowserController | None = None

    def _ensure_browser(self, headless: bool = True) -> BrowserController:
        if self._controller is None or not getattr(self._controller, "_launched", False):
            screenshots_dir = self.workspace_root / ".vibe_studio" / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            self._controller = BrowserController(
                headless=headless,
                screenshots_dir=screenshots_dir,
            )
            res = self._controller.launch(headless=headless)
            if not res.success:
                logger.warning("Browser launch failed or Playwright missing: %s", res.error)
        return self._controller

    # ------------------------------------------------------------------
    # Tool Methods
    # ------------------------------------------------------------------

    def browser_open(self, url: str, headless: bool = True) -> dict[str, Any]:
        """Launch browser and navigate to a URL."""
        ctrl = self._ensure_browser(headless=headless)
        res = ctrl.navigate(url)
        return {
            "action": "browser_open",
            "success": res.success,
            "url": url,
            "title": res.data.get("title", ""),
            "status": res.data.get("status"),
            "error": res.error,
        }

    def browser_navigate(self, url: str) -> dict[str, Any]:
        """Navigate active browser page to URL."""
        ctrl = self._ensure_browser()
        res = ctrl.navigate(url)
        return {
            "action": "browser_navigate",
            "success": res.success,
            "url": url,
            "title": res.data.get("title", ""),
            "status": res.data.get("status"),
            "error": res.error,
        }

    def browser_click(self, selector: str) -> dict[str, Any]:
        """Click element by CSS selector or XPath."""
        ctrl = self._ensure_browser()
        res = ctrl.click(selector)
        return {
            "action": "browser_click",
            "success": res.success,
            "selector": selector,
            "error": res.error,
        }

    def browser_type(self, selector: str, text: str, clear_first: bool = True) -> dict[str, Any]:
        """Type text into an input or textarea."""
        ctrl = self._ensure_browser()
        res = ctrl.type_text(selector, text, clear_first=clear_first)
        return {
            "action": "browser_type",
            "success": res.success,
            "selector": selector,
            "text": text,
            "error": res.error,
        }

    def browser_extract_text(self, selector: str = "body", max_chars: int = 10000) -> dict[str, Any]:
        """Extract visible text from the page or a specific container element."""
        ctrl = self._ensure_browser()
        res = ctrl.get_text(selector)
        text = res.data.get("text", "") if res.success else ""
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [Truncated {len(text) - max_chars} characters]"
        return {
            "action": "browser_extract_text",
            "success": res.success,
            "selector": selector,
            "text": text,
            "error": res.error,
        }

    def browser_screenshot(self, filename: str = "screenshot.png") -> dict[str, Any]:
        """Capture viewport screenshot and save into workspace or return base64."""
        ctrl = self._ensure_browser()
        save_path = self.workspace_root / filename if not Path(filename).is_absolute() else Path(filename)
        res = ctrl.screenshot(save_path=save_path)
        return {
            "action": "browser_screenshot",
            "success": res.success,
            "path": str(save_path),
            "error": res.error,
        }

    def browser_evaluate_js(self, script: str) -> dict[str, Any]:
        """Execute custom JavaScript in page context and return the result."""
        ctrl = self._ensure_browser()
        res = ctrl.evaluate(script)
        return {
            "action": "browser_evaluate_js",
            "success": res.success,
            "result": res.data.get("result"),
            "error": res.error,
        }

    def browser_wait(self, selector: str, timeout_ms: int = 5000) -> dict[str, Any]:
        """Wait for element matching selector to appear in the DOM."""
        ctrl = self._ensure_browser()
        res = ctrl.wait_for_selector(selector, timeout_ms=timeout_ms)
        return {
            "action": "browser_wait",
            "success": res.success,
            "selector": selector,
            "error": res.error,
        }

    def browser_console_logs(self, limit: int = 20) -> dict[str, Any]:
        """Retrieve browser console output and errors."""
        ctrl = self._ensure_browser()
        logs = ctrl.console_logs()
        return {
            "action": "browser_console_logs",
            "success": True,
            "logs": logs[-limit:],
        }

    def browser_close(self) -> dict[str, Any]:
        """Close browser session."""
        if self._controller:
            res = self._controller.close()
            self._controller = None
            return {"action": "browser_close", "success": res.success, "error": res.error}
        return {"action": "browser_close", "success": True, "note": "No active browser."}
