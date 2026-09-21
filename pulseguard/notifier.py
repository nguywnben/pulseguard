"""Multi-channel incident and recovery notification dispatcher."""

import asyncio
import json
import time
import urllib.request
from typing import Dict, Any, Optional
from .models import Monitor, Incident, Heartbeat


class Notifier:
    def __init__(self, channels_config: Optional[Dict[str, Any]] = None):
        """
        channels_config format:
        {
            "telegram": {"bot_token": "...", "chat_id": "..."},
            "discord": {"webhook_url": "..."},
            "slack": {"webhook_url": "..."},
            "ntfy": {"topic": "pulseguard_alerts", "server": "https://ntfy.sh"}
        }
        """
        self.config = channels_config or {}

    def update_config(self, new_config: Dict[str, Any]) -> None:
        self.config.update(new_config)

    async def send_incident_alert(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        """Dispatches DOWN/DEGRADED incident notifications across configured channels."""
        channels = monitor.alert_channels or list(self.config.keys())
        tasks = []
        for ch in channels:
            if ch == "telegram" and "telegram" in self.config:
                tasks.append(self._send_telegram_incident(monitor, incident, hb))
            elif ch == "discord" and "discord" in self.config:
                tasks.append(self._send_discord_incident(monitor, incident, hb))
            elif ch == "slack" and "slack" in self.config:
                tasks.append(self._send_slack_incident(monitor, incident, hb))
            elif ch == "ntfy" and "ntfy" in self.config:
                tasks.append(self._send_ntfy_incident(monitor, incident, hb))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_recovery_alert(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        """Dispatches RECOVERY notifications when monitor returns to healthy state."""
        channels = monitor.alert_channels or list(self.config.keys())
        tasks = []
        for ch in channels:
            if ch == "telegram" and "telegram" in self.config:
                tasks.append(self._send_telegram_recovery(monitor, incident, hb))
            elif ch == "discord" and "discord" in self.config:
                tasks.append(self._send_discord_recovery(monitor, incident, hb))
            elif ch == "slack" and "slack" in self.config:
                tasks.append(self._send_slack_recovery(monitor, incident, hb))
            elif ch == "ntfy" and "ntfy" in self.config:
                tasks.append(self._send_ntfy_recovery(monitor, incident, hb))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ---------------- Channel Implementations ---------------- #

    async def _send_telegram_incident(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        conf = self.config.get("telegram", {})
        token = conf.get("bot_token")
        chat_id = conf.get("chat_id")
        if not token or not chat_id:
            return

        text = (
            f"🚨 <b>PULSEGUARD INCIDENT ALERT</b> 🚨\n\n"
            f"<b>Monitor:</b> {monitor.name} ({monitor.type.upper()})\n"
            f"<b>Target:</b> <code>{monitor.target}</code>\n"
            f"<b>Status:</b> <b>DOWN / CRITICAL</b>\n"
            f"<b>Reason:</b> {hb.error_message or 'Check failed'}\n"
            f"<b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(hb.timestamp))}\n"
            f"<b>Latency:</b> {hb.latency_ms:.1f}ms\n"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        await self._http_post_json(url, payload)

    async def _send_telegram_recovery(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        conf = self.config.get("telegram", {})
        token = conf.get("bot_token")
        chat_id = conf.get("chat_id")
        if not token or not chat_id:
            return

        duration_s = int(hb.timestamp - incident.started_at)
        text = (
            f"✅ <b>PULSEGUARD INCIDENT RESOLVED</b> ✅\n\n"
            f"<b>Monitor:</b> {monitor.name}\n"
            f"<b>Target:</b> <code>{monitor.target}</code>\n"
            f"<b>Status:</b> <b>OPERATIONAL (UP)</b>\n"
            f"<b>Downtime Duration:</b> {duration_s} seconds\n"
            f"<b>Current Latency:</b> {hb.latency_ms:.1f}ms\n"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        await self._http_post_json(url, payload)

    async def _send_ntfy_incident(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        conf = self.config.get("ntfy", {})
        topic = conf.get("topic", "pulseguard_alerts")
        server = conf.get("server", "https://ntfy.sh").rstrip("/")
        url = f"{server}/{topic}"

        msg = f"🔴 {monitor.name} is DOWN! Reason: {hb.error_message or 'Failure'}"
        headers = {
            "Title": f"Incident: {monitor.name} is DOWN",
            "Priority": "urgent",
            "Tags": "warning,skull",
        }
        await self._http_post_raw(url, msg.encode("utf-8"), headers)

    async def _send_ntfy_recovery(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        conf = self.config.get("ntfy", {})
        topic = conf.get("topic", "pulseguard_alerts")
        server = conf.get("server", "https://ntfy.sh").rstrip("/")
        url = f"{server}/{topic}"

        duration_s = int(hb.timestamp - incident.started_at)
        msg = f"🟢 {monitor.name} is RECOVERED! Downtime: {duration_s}s"
        headers = {
            "Title": f"Recovered: {monitor.name}",
            "Priority": "default",
            "Tags": "white_check_mark",
        }
        await self._http_post_raw(url, msg.encode("utf-8"), headers)

    async def _send_discord_incident(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        webhook_url = self.config.get("discord", {}).get("webhook_url")
        if not webhook_url:
            return
        payload = {
            "content": f"🚨 **PulseGuard Alert**: `{monitor.name}` is **DOWN**!\nTarget: {monitor.target}\nReason: {hb.error_message}"
        }
        await self._http_post_json(webhook_url, payload)

    async def _send_discord_recovery(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        webhook_url = self.config.get("discord", {}).get("webhook_url")
        if not webhook_url:
            return
        duration_s = int(hb.timestamp - incident.started_at)
        payload = {
            "content": f"✅ **PulseGuard Resolved**: `{monitor.name}` is **UP**! (Downtime: {duration_s}s, Latency: {hb.latency_ms:.1f}ms)"
        }
        await self._http_post_json(webhook_url, payload)

    async def _send_slack_incident(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        webhook_url = self.config.get("slack", {}).get("webhook_url")
        if not webhook_url:
            return
        payload = {
            "text": f"🚨 *PulseGuard Alert*: Monitor *{monitor.name}* is *DOWN*!\nTarget: `{monitor.target}`\nError: {hb.error_message}"
        }
        await self._http_post_json(webhook_url, payload)

    async def _send_slack_recovery(self, monitor: Monitor, incident: Incident, hb: Heartbeat) -> None:
        webhook_url = self.config.get("slack", {}).get("webhook_url")
        if not webhook_url:
            return
        duration_s = int(hb.timestamp - incident.started_at)
        payload = {
            "text": f"✅ *PulseGuard Recovered*: Monitor *{monitor.name}* is *UP*! Downtime: {duration_s}s"
        }
        await self._http_post_json(webhook_url, payload)

    # ---------------- Generic Async HTTP POST Helpers ---------------- #

    async def _http_post_json(self, url: str, data: Dict[str, Any]) -> None:
        loop = asyncio.get_running_loop()
        body = json.dumps(data).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "PulseGuard-Notifier/1.0"}
        await loop.run_in_executor(None, self._sync_post, url, body, headers)

    async def _http_post_raw(self, url: str, body: bytes, custom_headers: Dict[str, str]) -> None:
        loop = asyncio.get_running_loop()
        headers = {"User-Agent": "PulseGuard-Notifier/1.0"}
        headers.update(custom_headers)
        await loop.run_in_executor(None, self._sync_post, url, body, headers)

    def _sync_post(self, url: str, data: bytes, headers: Dict[str, str]) -> None:
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception:
            pass  # Suppress notification delivery errors so prober loop never halts
