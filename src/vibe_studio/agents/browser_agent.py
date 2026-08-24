"""BrowserController — Playwright-based browser automation for the Vibe Studio agent.

Provides the agent with "eyes and hands" to interact with web applications:

    BrowserController
     ├── launch()           Start Chromium/Firefox/WebKit
     ├── navigate()         Go to URL
     ├── click()            Click element by selector / coordinates
     ├── type_text()        Type into focused / selected input
     ├── screenshot()       Capture viewport PNG → base64 or file
     ├── inspect()          Get DOM structure / element details
     ├── console_logs()     Return JS console log history
     ├── network_logs()     Return network request log
     ├── record()           Start / stop HAR session recording
     └── close()            Tear down browser

Design goals:
  - Works **without** a display (headless=True by default)
  - Falls back gracefully when Playwright is not installed
  - All calls are synchronous (wraps async Playwright via run_sync)
  - Returns structured dicts so ToolRegistry / agent can parse the output
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Playwright import
# ---------------------------------------------------------------------------

try:
    from playwright.sync_api import (  # type: ignore[import]
        Browser,
        BrowserContext,
        ConsoleMessage,
        Page,
        Request,
        Response,
        sync_playwright,
    )
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning(
        "Playwright not installed. BrowserController will run in stub mode. "
        "Install with: pip install playwright && playwright install chromium"
    )


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BrowserResult:
    """Structured return type for all BrowserController methods."""
    success: bool
    action: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "data": self.data,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


@dataclass
class NetworkEntry:
    url: str
    method: str
    status: int
    resource_type: str
    duration_ms: float
    request_headers: dict[str, str] = field(default_factory=dict)
    response_size: int = 0


# ---------------------------------------------------------------------------
# BrowserController
# ---------------------------------------------------------------------------

class BrowserController:
    """
    Browser automation controller for the Vibe Studio agent.

    Usage (sync API)::

        with BrowserController(headless=True) as browser:
            browser.launch()
            browser.navigate("https://example.com")
            browser.click("#login-btn")
            browser.type_text("#password", "secret")
            shot = browser.screenshot()
            logs = browser.console_logs()

    All methods return a :class:`BrowserResult` — never raise unless
    ``raise_on_error=True`` is set.
    """

    def __init__(
        self,
        browser_type: str = "chromium",   # chromium | firefox | webkit
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        default_timeout_ms: int = 15_000,
        screenshots_dir: str | Path | None = None,
        raise_on_error: bool = False,
    ):
        self.browser_type = browser_type
        self.headless = headless
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self.default_timeout = default_timeout_ms
        self.screenshots_dir = Path(screenshots_dir) if screenshots_dir else None
        self.raise_on_error = raise_on_error

        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._launched = False

        # Logs accumulated during the session
        self._console_entries: list[dict[str, Any]] = []
        self._network_entries: list[NetworkEntry] = []
        self._request_map: dict[str, float] = {}  # url → start_time

        # HAR recording
        self._har_path: Path | None = None
        self._recording = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "BrowserController":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # launch / close
    # ------------------------------------------------------------------

    def launch(
        self,
        browser_type: str | None = None,
        headless: bool | None = None,
    ) -> BrowserResult:
        """Start the browser process."""
        t0 = time.monotonic()
        bt = browser_type or self.browser_type
        hl = self.headless if headless is None else headless

        if not _PLAYWRIGHT_AVAILABLE:
            return self._stub("launch", error="Playwright not installed. Run: pip install playwright && playwright install chromium")

        if self._launched:
            return BrowserResult(True, "launch", data={"note": "already launched"}, elapsed_ms=0)

        try:
            self._playwright = sync_playwright().start()
            launcher = getattr(self._playwright, bt)
            self._browser = launcher.launch(
                headless=hl,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            self._context = self._browser.new_context(viewport=self.viewport)
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.default_timeout)

            # Wire up log listeners
            self._page.on("console", self._on_console)
            self._context.on("request", self._on_request)
            self._context.on("response", self._on_response)

            self._launched = True
            elapsed = (time.monotonic() - t0) * 1000
            logger.info("Browser launched: %s (headless=%s)", bt, hl)
            return BrowserResult(True, "launch", data={"browser": bt, "headless": hl}, elapsed_ms=elapsed)

        except Exception as exc:
            return self._err("launch", exc)

    def close(self) -> BrowserResult:
        """Tear down browser and Playwright instance."""
        t0 = time.monotonic()
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
            self._launched = False
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "close", elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("close", exc)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> BrowserResult:
        """Navigate to *url* and wait until the page is ready."""
        t0 = time.monotonic()
        if not self._check_ready("navigate"):
            return self._not_launched("navigate")
        try:
            response = self._page.goto(url, wait_until=wait_until)  # type: ignore[union-attr]
            elapsed = (time.monotonic() - t0) * 1000
            status = response.status if response else None
            title = self._page.title()
            return BrowserResult(
                True, "navigate",
                data={"url": url, "status": status, "title": title},
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            return self._err("navigate", exc)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def click(
        self,
        selector: str,
        button: str = "left",
        click_count: int = 1,
        delay_ms: int = 0,
        x: float | None = None,
        y: float | None = None,
    ) -> BrowserResult:
        """Click element by CSS selector, or at (x, y) coordinates."""
        t0 = time.monotonic()
        if not self._check_ready("click"):
            return self._not_launched("click")
        try:
            if x is not None and y is not None:
                self._page.mouse.click(x, y, button=button, click_count=click_count, delay=delay_ms)  # type: ignore[union-attr]
                target = f"({x}, {y})"
            else:
                self._page.click(selector, button=button, click_count=click_count, delay=delay_ms)  # type: ignore[union-attr]
                target = selector
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "click", data={"target": target}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("click", exc)

    def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        delay_ms: int = 0,
    ) -> BrowserResult:
        """Type *text* into the element matching *selector*."""
        t0 = time.monotonic()
        if not self._check_ready("type_text"):
            return self._not_launched("type_text")
        try:
            if clear_first:
                self._page.fill(selector, "")  # type: ignore[union-attr]
            self._page.type(selector, text, delay=delay_ms)  # type: ignore[union-attr]
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(
                True, "type_text",
                data={"selector": selector, "chars": len(text)},
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            return self._err("type_text", exc)

    def press_key(self, key: str, selector: str | None = None) -> BrowserResult:
        """Press a keyboard key (e.g. 'Enter', 'Tab', 'Escape')."""
        t0 = time.monotonic()
        if not self._check_ready("press_key"):
            return self._not_launched("press_key")
        try:
            if selector:
                self._page.press(selector, key)  # type: ignore[union-attr]
            else:
                self._page.keyboard.press(key)  # type: ignore[union-attr]
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "press_key", data={"key": key}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("press_key", exc)

    def scroll(self, x: float = 0, y: float = 400, selector: str | None = None) -> BrowserResult:
        """Scroll the page or a specific element."""
        t0 = time.monotonic()
        if not self._check_ready("scroll"):
            return self._not_launched("scroll")
        try:
            if selector:
                self._page.eval_on_selector(  # type: ignore[union-attr]
                    selector,
                    f"el => el.scrollBy({x}, {y})",
                )
            else:
                self._page.mouse.wheel(x, y)  # type: ignore[union-attr]
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "scroll", data={"dx": x, "dy": y}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("scroll", exc)

    def wait_for(self, selector: str, state: str = "visible", timeout_ms: int | None = None) -> BrowserResult:
        """Wait for element to reach *state* (visible | hidden | attached | detached)."""
        t0 = time.monotonic()
        if not self._check_ready("wait_for"):
            return self._not_launched("wait_for")
        try:
            self._page.wait_for_selector(  # type: ignore[union-attr]
                selector, state=state,
                timeout=timeout_ms or self.default_timeout,
            )
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "wait_for", data={"selector": selector, "state": state}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("wait_for", exc)

    # ------------------------------------------------------------------
    # Capture / Inspect
    # ------------------------------------------------------------------

    def screenshot(
        self,
        save_path: str | Path | None = None,
        full_page: bool = False,
        selector: str | None = None,
    ) -> BrowserResult:
        """
        Capture the current viewport (or element) as a PNG.

        Returns base64-encoded image in ``data["base64"]`` and saves to
        *save_path* if provided.
        """
        t0 = time.monotonic()
        if not self._check_ready("screenshot"):
            return self._not_launched("screenshot")
        try:
            if selector:
                element = self._page.query_selector(selector)  # type: ignore[union-attr]
                raw = element.screenshot() if element else self._page.screenshot(full_page=full_page)
            else:
                raw = self._page.screenshot(full_page=full_page)  # type: ignore[union-attr]

            b64 = base64.b64encode(raw).decode()

            saved_path: str | None = None
            if save_path:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
                saved_path = str(p)
            elif self.screenshots_dir:
                self.screenshots_dir.mkdir(parents=True, exist_ok=True)
                ts = int(time.time())
                p = self.screenshots_dir / f"screenshot_{ts}.png"
                p.write_bytes(raw)
                saved_path = str(p)

            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(
                True, "screenshot",
                data={
                    "base64": b64,
                    "size_bytes": len(raw),
                    "saved_path": saved_path,
                    "full_page": full_page,
                },
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            return self._err("screenshot", exc)

    def inspect(
        self,
        selector: str | None = None,
        include_text: bool = True,
        max_depth: int = 5,
    ) -> BrowserResult:
        """
        Inspect the DOM structure.

        - If *selector* is given, returns details for that element.
        - Otherwise returns a condensed structural snapshot of the body.
        """
        t0 = time.monotonic()
        if not self._check_ready("inspect"):
            return self._not_launched("inspect")
        try:
            if selector:
                details = self._page.eval_on_selector(  # type: ignore[union-attr]
                    selector,
                    """el => ({
                        tag: el.tagName,
                        id: el.id,
                        classes: [...el.classList],
                        text: el.innerText?.slice(0, 200),
                        value: el.value,
                        href: el.href,
                        disabled: el.disabled,
                        visible: el.offsetParent !== null,
                        rect: el.getBoundingClientRect().toJSON(),
                        attrs: Object.fromEntries([...el.attributes].map(a => [a.name, a.value])),
                    })""",
                )
                elapsed = (time.monotonic() - t0) * 1000
                return BrowserResult(True, "inspect", data={"element": details, "selector": selector}, elapsed_ms=elapsed)
            else:
                # Return structural snapshot
                structure = self._page.evaluate(  # type: ignore[union-attr]
                    f"""() => {{
                        function walk(el, depth) {{
                            if (depth > {max_depth}) return null;
                            const children = [...el.children].map(c => walk(c, depth+1)).filter(Boolean);
                            return {{
                                tag: el.tagName,
                                id: el.id || null,
                                classes: [...el.classList].slice(0, 5),
                                text: {'el.innerText?.slice(0, 50)' if include_text else 'null'},
                                children: children.slice(0, 10),
                            }};
                        }}
                        return walk(document.body, 0);
                    }}"""
                )
                elapsed = (time.monotonic() - t0) * 1000
                return BrowserResult(True, "inspect", data={"structure": structure}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("inspect", exc)

    def get_text(self, selector: str) -> BrowserResult:
        """Get the text content of an element."""
        t0 = time.monotonic()
        if not self._check_ready("get_text"):
            return self._not_launched("get_text")
        try:
            text = self._page.text_content(selector) or ""  # type: ignore[union-attr]
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "get_text", data={"selector": selector, "text": text}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("get_text", exc)

    def evaluate(self, script: str) -> BrowserResult:
        """Execute arbitrary JavaScript in the page context."""
        t0 = time.monotonic()
        if not self._check_ready("evaluate"):
            return self._not_launched("evaluate")
        try:
            result = self._page.evaluate(script)  # type: ignore[union-attr]
            elapsed = (time.monotonic() - t0) * 1000
            return BrowserResult(True, "evaluate", data={"result": result}, elapsed_ms=elapsed)
        except Exception as exc:
            return self._err("evaluate", exc)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def console_logs(
        self,
        level_filter: str | None = None,  # "log" | "error" | "warning" | "info"
        limit: int = 100,
    ) -> BrowserResult:
        """Return JS console log entries captured since launch."""
        entries = self._console_entries
        if level_filter:
            entries = [e for e in entries if e.get("level") == level_filter]
        return BrowserResult(
            True, "console_logs",
            data={"entries": entries[-limit:], "total": len(self._console_entries)},
        )

    def network_logs(
        self,
        method_filter: str | None = None,
        status_filter: int | None = None,
        limit: int = 100,
    ) -> BrowserResult:
        """Return network request log entries captured since launch."""
        entries = self._network_entries
        if method_filter:
            entries = [e for e in entries if e.method.upper() == method_filter.upper()]
        if status_filter:
            entries = [e for e in entries if e.status == status_filter]
        data = [
            {
                "url": e.url,
                "method": e.method,
                "status": e.status,
                "type": e.resource_type,
                "duration_ms": round(e.duration_ms, 1),
                "size": e.response_size,
            }
            for e in entries[-limit:]
        ]
        return BrowserResult(
            True, "network_logs",
            data={"entries": data, "total": len(self._network_entries)},
        )

    # ------------------------------------------------------------------
    # HAR Recording
    # ------------------------------------------------------------------

    def record(
        self,
        action: str = "start",
        save_path: str | Path | None = None,
    ) -> BrowserResult:
        """
        Start or stop HAR recording.

        Args:
            action   : "start" or "stop"
            save_path: Where to save the HAR file (only used on stop)

        HAR files can be loaded in browser DevTools or tools like Insomnia.
        """
        t0 = time.monotonic()
        if not self._check_ready("record"):
            return self._not_launched("record")

        if action == "start":
            if self._recording:
                return BrowserResult(True, "record", data={"note": "already recording"})
            try:
                # Playwright records HAR at context level
                # We track network ourselves (already wired), so "recording"
                # is just flagging that we will dump a synthetic HAR on stop.
                self._recording = True
                self._network_entries.clear()
                self._console_entries.clear()
                elapsed = (time.monotonic() - t0) * 1000
                return BrowserResult(True, "record", data={"status": "started"}, elapsed_ms=elapsed)
            except Exception as exc:
                return self._err("record", exc)

        elif action == "stop":
            if not self._recording:
                return BrowserResult(True, "record", data={"note": "not recording"})
            try:
                har = self._build_har()
                self._recording = False
                saved_path: str | None = None
                if save_path:
                    p = Path(save_path)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps(har, indent=2))
                    saved_path = str(p)
                elapsed = (time.monotonic() - t0) * 1000
                return BrowserResult(
                    True, "record",
                    data={
                        "status": "stopped",
                        "requests_captured": len(self._network_entries),
                        "saved_path": saved_path,
                        "har": har if not saved_path else None,
                    },
                    elapsed_ms=elapsed,
                )
            except Exception as exc:
                return self._err("record", exc)
        else:
            return BrowserResult(False, "record", error=f"Unknown action: {action!r}. Use 'start' or 'stop'.")

    # ------------------------------------------------------------------
    # Current page info helpers
    # ------------------------------------------------------------------

    def current_url(self) -> str:
        if self._page:
            return self._page.url
        return ""

    def page_title(self) -> str:
        if self._page:
            try:
                return self._page.title()
            except Exception:
                pass
        return ""

    def is_launched(self) -> bool:
        return self._launched

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_ready(self, action: str) -> bool:
        if not _PLAYWRIGHT_AVAILABLE:
            return False
        if not self._launched or not self._page:
            return False
        return True

    def _not_launched(self, action: str) -> BrowserResult:
        if not _PLAYWRIGHT_AVAILABLE:
            return self._stub(action, error="Playwright not installed")
        return BrowserResult(False, action, error="Browser not launched. Call launch() first.")

    def _err(self, action: str, exc: Exception) -> BrowserResult:
        msg = f"{type(exc).__name__}: {exc}"
        logger.error("BrowserController.%s failed: %s", action, msg)
        if self.raise_on_error:
            raise exc
        return BrowserResult(False, action, error=msg)

    @staticmethod
    def _stub(action: str, error: str = "") -> BrowserResult:
        return BrowserResult(False, action, error=error or "Playwright not available")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_console(self, msg: "ConsoleMessage") -> None:
        self._console_entries.append({
            "level": msg.type,
            "text": msg.text,
            "url": msg.location.get("url", "") if msg.location else "",
            "line": msg.location.get("lineNumber", 0) if msg.location else 0,
            "timestamp": time.time(),
        })

    def _on_request(self, request: "Request") -> None:
        self._request_map[request.url] = time.monotonic()

    def _on_response(self, response: "Response") -> None:
        start = self._request_map.pop(response.request.url, time.monotonic())
        duration_ms = (time.monotonic() - start) * 1000
        try:
            size = len(response.body()) if response.ok else 0
        except Exception:
            size = 0
        self._network_entries.append(
            NetworkEntry(
                url=response.url,
                method=response.request.method,
                status=response.status,
                resource_type=response.request.resource_type,
                duration_ms=duration_ms,
                response_size=size,
            )
        )

    def _build_har(self) -> dict[str, Any]:
        """Build a minimal HAR 1.2 object from captured network entries."""
        entries = []
        for ne in self._network_entries:
            entries.append({
                "startedDateTime": "",
                "time": ne.duration_ms,
                "request": {
                    "method": ne.method,
                    "url": ne.url,
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "queryString": [],
                    "cookies": [],
                    "headersSize": -1,
                    "bodySize": -1,
                },
                "response": {
                    "status": ne.status,
                    "statusText": "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "cookies": [],
                    "content": {"mimeType": "", "size": ne.response_size},
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": ne.response_size,
                },
                "cache": {},
                "timings": {"send": 0, "wait": ne.duration_ms, "receive": 0},
            })
        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "vibe-studio-browser-agent", "version": "1.0"},
                "entries": entries,
            }
        }


# ---------------------------------------------------------------------------
# Tool schema (for ToolRegistry integration)
# ---------------------------------------------------------------------------

BROWSER_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "browser_launch",
        "description": "Launch a browser instance. Must be called before any other browser tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "browser_type": {
                    "type": "string",
                    "enum": ["chromium", "firefox", "webkit"],
                    "description": "Browser engine to use",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run without a visible window (default: true)",
                },
            },
        },
        "risk": "LOW",
    },
    {
        "name": "browser_navigate",
        "description": "Navigate to a URL and wait for the page to load.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
        "risk": "LOW",
    },
    {
        "name": "browser_click",
        "description": "Click an element identified by a CSS selector.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the element to click"},
            },
            "required": ["selector"],
        },
        "risk": "LOW",
    },
    {
        "name": "browser_type",
        "description": "Type text into an input field.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the input"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["selector", "text"],
        },
        "risk": "LOW",
    },
    {
        "name": "browser_screenshot",
        "description": "Capture a screenshot of the current page. Returns base64 PNG.",
        "parameters": {
            "type": "object",
            "properties": {
                "full_page": {"type": "boolean", "description": "Capture full scrollable page"},
                "selector": {"type": "string", "description": "Capture only this element"},
            },
        },
        "risk": "SAFE",
    },
    {
        "name": "browser_inspect",
        "description": "Inspect the DOM structure or a specific element.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to inspect (optional; omit for full page structure)"},
            },
        },
        "risk": "SAFE",
    },
    {
        "name": "browser_console_logs",
        "description": "Return JavaScript console log entries since browser launch.",
        "parameters": {
            "type": "object",
            "properties": {
                "level_filter": {
                    "type": "string",
                    "enum": ["log", "error", "warning", "info"],
                    "description": "Filter by log level",
                },
                "limit": {"type": "integer", "description": "Max entries to return"},
            },
        },
        "risk": "SAFE",
    },
    {
        "name": "browser_network_logs",
        "description": "Return network request log entries since browser launch.",
        "parameters": {
            "type": "object",
            "properties": {
                "method_filter": {"type": "string", "description": "Filter by HTTP method (GET, POST, etc.)"},
                "status_filter": {"type": "integer", "description": "Filter by HTTP status code"},
                "limit": {"type": "integer"},
            },
        },
        "risk": "SAFE",
    },
    {
        "name": "browser_record",
        "description": "Start or stop HAR session recording of all network requests.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "stop"], "description": "Start or stop recording"},
                "save_path": {"type": "string", "description": "File path to save the HAR (only on stop)"},
            },
            "required": ["action"],
        },
        "risk": "LOW",
    },
    {
        "name": "browser_evaluate",
        "description": "Execute JavaScript in the browser page context and return the result.",
        "parameters": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "JavaScript expression to evaluate"},
            },
            "required": ["script"],
        },
        "risk": "MEDIUM",
    },
    {
        "name": "browser_close",
        "description": "Close the browser and free resources.",
        "parameters": {"type": "object", "properties": {}},
        "risk": "SAFE",
    },
]
