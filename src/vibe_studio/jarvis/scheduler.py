"""JarvisScheduler — Real-time Timer, Alarm & Background Task Scheduler.

Supports:
1. Relative Countdown Timers ("10 dəqiqə sonra çayı xatırlat", "set timer for 5 minutes")
2. Absolute Time Alarms ("saat 15:30-da zəng vur", "set alarm for 09:00")
3. Thread-safe background monitoring daemon
4. Automated Voice announcements and Native Desktop OS Notifications
"""
from __future__ import annotations

import datetime
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class ScheduledItem:
    id: str
    label: str
    target_time: float
    created_at: float = field(default_factory=time.time)
    is_alarm: bool = False
    alarm_time_str: str = ""
    status: str = "active"  # "active", "completed", "cancelled"

    def remaining_seconds(self) -> float:
        return max(0.0, self.target_time - time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "target_time": self.target_time,
            "remaining_seconds": round(self.remaining_seconds(), 1),
            "is_alarm": self.is_alarm,
            "alarm_time_str": self.alarm_time_str,
            "status": self.status,
        }


class JarvisScheduler:
    """Thread-safe background timer and reminder engine."""

    def __init__(self, on_trigger: Callable[[ScheduledItem], None] | None = None) -> None:
        self.on_trigger = on_trigger
        self._tasks: dict[str, ScheduledItem] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="JarvisSchedulerThread")
        self._thread.start()

    def stop(self) -> None:
        """Stop background scheduler."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def set_timer(self, seconds: float, label: str = "Timer") -> ScheduledItem:
        """Schedule a relative countdown timer."""
        self.start()
        item_id = str(uuid.uuid4())[:8]
        target = time.time() + max(0.05, float(seconds))
        item = ScheduledItem(
            id=item_id,
            label=label.strip(),
            target_time=target,
            is_alarm=False,
            status="active",
        )

        with self._lock:
            self._tasks[item_id] = item
        return item

    def set_alarm(self, target_time_str: str, label: str = "Alarm") -> ScheduledItem | None:
        """Schedule an absolute time alarm for today (or tomorrow if time has passed).
        
        target_time_str format: "HH:MM" (e.g. "14:30", "09:00").
        """
        self.start()
        try:
            parts = target_time_str.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1])
        except Exception:
            return None

        now = datetime.datetime.now()
        target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_dt <= now:
            # Schedule for tomorrow
            target_dt += datetime.timedelta(days=1)

        delta_seconds = (target_dt - now).total_seconds()
        item_id = str(uuid.uuid4())[:8]
        item = ScheduledItem(
            id=item_id,
            label=label.strip(),
            target_time=time.time() + delta_seconds,
            is_alarm=True,
            alarm_time_str=f"{hour:02d}:{minute:02d}",
            status="active",
        )
        with self._lock:
            self._tasks[item_id] = item
        return item

    def list_active_timers(self) -> list[ScheduledItem]:
        """Return all active scheduled items."""
        with self._lock:
            return [t for t in self._tasks.values() if t.status == "active"]

    def cancel_timer(self, item_id: str) -> bool:
        """Cancel a timer by ID or matching label."""
        with self._lock:
            for k, item in list(self._tasks.items()):
                if k == item_id or item.label.lower() == item_id.lower():
                    item.status = "cancelled"
                    return True
        return False

    def _run_loop(self) -> None:
        """Main scheduler checking loop."""
        while self._running:
            time.sleep(0.1)
            now = time.time()

            triggered_items: list[ScheduledItem] = []

            with self._lock:
                for item in list(self._tasks.values()):
                    if item.status == "active" and now >= item.target_time:
                        item.status = "completed"
                        triggered_items.append(item)

            for trig in triggered_items:
                if self.on_trigger:
                    try:
                        self.on_trigger(trig)
                    except Exception:
                        pass
