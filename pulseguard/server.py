"""High-performance async HTTP Server hosting the REST API, dynamic Badges, and Status Page."""

import asyncio
import json
import os
import time
import urllib.parse
from typing import Optional, Dict, Any
from .db import Database
from .models import Monitor, MonitorType
from .web.badges import generate_status_badge
from .engine import SentinelEngine


class HttpServer:
    def __init__(self, db: Database, engine: SentinelEngine, host: str = "0.0.0.0", port: int = 8920):
        self.db = db
        self.engine = engine
        self.host = host
        self.port = port
        self._server: Optional[asyncio.Server] = None
        self._html_cache: Optional[bytes] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        print(f"[PulseGuard] Status Page & REST API running on http://{self.host}:{self.port}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                writer.close()
                return

            req_line = line.decode("utf-8", errors="ignore").strip()
            parts = req_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method = parts[0].upper()
            full_path = parts[1]

            # Read headers
            headers: Dict[str, str] = {}
            content_length = 0
            while True:
                header_line = await reader.readline()
                if not header_line or header_line == b"\r\n":
                    break
                h_str = header_line.decode("utf-8", errors="ignore").strip()
                if ":" in h_str:
                    k, v = h_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        content_length = int(v.strip())

            # Read Body if POST/PUT
            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            parsed_url = urllib.parse.urlparse(full_path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)

            # Route Dispatch
            status_code, content_type, response_data = await self._route(method, path, query, body_bytes)

            header_bytes = (
                f"HTTP/1.1 {status_code}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(response_data)}\r\n"
                f"Access-Control-Allow-Origin: *\r\n"
                f"Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
                f"Access-Control-Allow-Headers: Content-Type\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")

            writer.write(header_bytes + response_data)
            await writer.drain()

        except Exception as e:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _route(
        self, method: str, path: str, query: Dict[str, Any], body: bytes
    ) -> tuple[str, str, bytes]:
        # Handle CORS preflight
        if method == "OPTIONS":
            return "204 No Content", "text/plain", b""

        # 1. Healthcheck
        if path == "/healthz":
            return "200 OK", "application/json", b'{"status":"healthy","service":"pulseguard"}'

        # 2. Status Page UI (Root)
        if path in ("/", "/index.html"):
            if not self._html_cache:
                html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
                with open(html_path, "rb") as f:
                    self._html_cache = f.read()
            return "200 OK", "text/html; charset=utf-8", self._html_cache

        # 3. Overall & Monitors Status API
        if path == "/api/status" and method == "GET":
            data = await self._get_full_status_snapshot()
            return "200 OK", "application/json", json.dumps(data, indent=2).encode("utf-8")

        # 4. Monitors CRUD API
        if path == "/api/monitors":
            if method == "GET":
                monitors = self.db.list_monitors()
                return "200 OK", "application/json", json.dumps([m.to_dict() for m in monitors]).encode("utf-8")

            elif method == "POST":
                try:
                    payload = json.loads(body.decode("utf-8"))
                    monitor = Monitor.from_dict(payload)
                    self.db.upsert_monitor(monitor)
                    # Trigger an immediate probe
                    asyncio.create_task(self.engine.run_single_probe(monitor))
                    return "201 Created", "application/json", json.dumps(monitor.to_dict()).encode("utf-8")
                except Exception as e:
                    return "400 Bad Request", "application/json", json.dumps({"error": str(e)}).encode("utf-8")

        # 5. Delete Monitor: DELETE /api/monitors/{id}
        if path.startswith("/api/monitors/") and method == "DELETE":
            mon_id = path.split("/")[-1]
            success = self.db.delete_monitor(mon_id)
            if success:
                return "200 OK", "application/json", b'{"success":true}'
            return "404 Not Found", "application/json", b'{"error":"Monitor not found"}'

        # 6. Manual Trigger Probe: POST /api/monitors/{id}/probe
        if path.startswith("/api/monitors/") and path.endswith("/probe") and method == "POST":
            mon_id = path.split("/")[-2]
            monitor = self.db.get_monitor(mon_id)
            if not monitor:
                return "404 Not Found", "application/json", b'{"error":"Monitor not found"}'
            hb = await self.engine.run_single_probe(monitor)
            return "200 OK", "application/json", json.dumps(hb.to_dict()).encode("utf-8")

        # 7. Dynamic SVG Status Badge: GET /api/badge/{monitor_id}
        if path.startswith("/api/badge/"):
            mon_id = path.split("/")[-1]
            monitor = self.db.get_monitor(mon_id)
            if not monitor:
                svg = generate_status_badge(label="Monitor", status_text="NOT FOUND", is_up=False)
                return "404 Not Found", "image/svg+xml; charset=utf-8", svg.encode("utf-8")

            latest = self.db.get_latest_heartbeat(mon_id)
            stats = self.db.get_aggregated_stats(mon_id)
            uptime_pct = stats.get("uptime_30d", 100.0)
            is_up = latest.is_up if latest else True

            badge_type = query.get("type", ["uptime"])[0]
            if badge_type == "status":
                svg = generate_status_badge(
                    label=monitor.name,
                    status_text="UP" if is_up else "DOWN",
                    is_up=is_up,
                    uptime_pct=None,
                )
            else:
                svg = generate_status_badge(
                    label=monitor.name,
                    status_text=f"{uptime_pct:.2f}%",
                    is_up=is_up,
                    uptime_pct=uptime_pct,
                )
            return "200 OK", "image/svg+xml; charset=utf-8", svg.encode("utf-8")

        # 8. Incidents History: GET /api/incidents
        if path == "/api/incidents" and method == "GET":
            incidents = self.db.list_incidents(limit=30)
            return "200 OK", "application/json", json.dumps([i.to_dict() for i in incidents]).encode("utf-8")

        return "404 Not Found", "application/json", b'{"error":"Path not found"}'

    async def _get_full_status_snapshot(self) -> Dict[str, Any]:
        monitors = self.db.list_monitors()
        result_monitors = []
        overall_up = True

        for m in monitors:
            latest = self.db.get_latest_heartbeat(m.id)
            stats = self.db.get_aggregated_stats(m.id)
            if latest and not latest.is_up and m.enabled:
                overall_up = False

            m_dict = m.to_dict()
            m_dict["latest_heartbeat"] = latest.to_dict() if latest else None
            m_dict["stats"] = stats
            result_monitors.append(m_dict)

        incidents = self.db.list_incidents(limit=10)

        return {
            "overall_status": "up" if overall_up else "degraded",
            "timestamp": time.time(),
            "monitors_count": len(monitors),
            "monitors": result_monitors,
            "active_incidents": [i.to_dict() for i in incidents if i.state.value == "ongoing"],
            "recent_incidents": [i.to_dict() for i in incidents],
        }
