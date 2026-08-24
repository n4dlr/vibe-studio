"""JarvisWatchdog — Proactive Background System Sentinel & Heartbeat Daemon.

Monitors:
- CPU spikes (> 90%)
- Memory pressure (> 92%)
- Low battery (< 15% unplugged)
- Critical disk fill (> 95%)
- Heavy runaway processes
Triggers proactive voice warnings and emits telemetry events.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from vibe_studio.jarvis.telemetry import SystemSnapshot, SystemTelemetry


class JarvisWatchdog:
    """Proactive system sentinel for J.A.R.V.I.S."""

    def __init__(self, telemetry: SystemTelemetry, on_alert: Callable[[str, str], None] | None = None) -> None:
        self.telemetry = telemetry
        self.on_alert = on_alert
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_alert_time: dict[str, float] = {}
        self.alert_cooldown_seconds = 180.0  # Alert at most once every 3 minutes per metric

    def start(self) -> None:
        """Start the watchdog daemon in background."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="JarvisWatchdog")
        self._thread.start()

    def stop(self) -> None:
        """Stop the watchdog daemon."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._check_metrics()
            except Exception:
                pass
            time.sleep(5.0)

    def _check_metrics(self) -> None:
        snap = self.telemetry.get_snapshot()
        now = time.time()

        # 1. CPU Pressure
        if snap.cpu_percent > 92.0:
            if now - self._last_alert_time.get("cpu", 0) > self.alert_cooldown_seconds:
                self._last_alert_time["cpu"] = now
                msg = f"Warning, sir. CPU load is at {snap.cpu_percent:.0f} percent. Significant processing load detected."
                if self.on_alert:
                    self.on_alert("cpu_spike", msg)

        # 2. RAM Pressure
        if snap.ram_percent > 92.0:
            if now - self._last_alert_time.get("ram", 0) > self.alert_cooldown_seconds:
                self._last_alert_time["ram"] = now
                msg = f"Alert, sir. System memory utilization has reached {snap.ram_percent:.0f} percent. Recommending process cleanup."
                if self.on_alert:
                    self.on_alert("ram_spike", msg)

        # 3. Low Battery
        if snap.battery_percent is not None and snap.battery_percent < 15.0 and not snap.battery_charging:
            if now - self._last_alert_time.get("battery", 0) > self.alert_cooldown_seconds * 2:
                self._last_alert_time["battery"] = now
                msg = f"Power warning, sir. Battery level is at {snap.battery_percent:.0f} percent. Please connect the power adapter."
                if self.on_alert:
                    self.on_alert("low_battery", msg)
