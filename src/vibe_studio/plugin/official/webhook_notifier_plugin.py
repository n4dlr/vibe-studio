"""Webhook Notifier Plugin — sends Slack/Discord/Custom HTTP webhooks on task completion.

Pillar 3 (Enterprise Official Plugins):
  Provides tools to send structured notifications to webhooks.
"""
from __future__ import annotations

import json
import urllib.request
from vibe_studio.plugin.plugin_api import vibe_plugin


@vibe_plugin(
    name="send_webhook_notification",
    description="Send a JSON notification payload to a Slack, Discord, or custom HTTP webhook URL.",
    risk="MEDIUM",
)
def send_webhook_notification(webhook_url: str, title: str, message: str, status: str = "success") -> str:
    if not webhook_url.startswith(("http://", "https://")):
        return "Error: Invalid webhook URL scheme."

    payload = {
        "title": title,
        "message": message,
        "status": status,
        "source": "Vibe Studio 3.0",
        "text": f"*{title}*\n{message}\nStatus: `{status}`",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "VibeStudioNotifier/3.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return f"Notification sent successfully (HTTP {resp.status})."
    except Exception as exc:
        return f"Failed to send webhook notification: {exc}"
