"""Tests for HTTP Server, REST API, and Dynamic SVG Badges."""

import unittest
import asyncio
import urllib.request
import json
import os
import time
from pulseguard.db import Database
from pulseguard.engine import SentinelEngine
from pulseguard.notifier import Notifier
from pulseguard.server import HttpServer
from pulseguard.models import Monitor, MonitorType, Heartbeat


class TestHttpServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_db = f"/tmp/test_server_{int(time.time() * 1000)}.db"
        self.db = Database(self.test_db)
        self.notifier = Notifier({})
        self.engine = SentinelEngine(self.db, self.notifier)
        self.port = 8995
        self.server = HttpServer(self.db, self.engine, host="127.0.0.1", port=self.port)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    async def test_healthz_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/healthz"
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: urllib.request.urlopen(url).read())
        data = json.loads(res.decode("utf-8"))
        self.assertEqual(data["status"], "healthy")

    async def test_crud_monitors_and_badge(self):
        base_url = f"http://127.0.0.1:{self.port}"
        loop = asyncio.get_running_loop()

        # 1. Create Monitor via POST /api/monitors
        new_mon = {
            "id": "test_mon_api",
            "name": "API Test",
            "type": "https",
            "target": "https://nguywnben.dev",
            "interval_seconds": 60,
        }
        req = urllib.request.Request(
            f"{base_url}/api/monitors",
            data=json.dumps(new_mon).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        await loop.run_in_executor(None, lambda: urllib.request.urlopen(req).read())

        # 2. Get Monitors via GET /api/monitors
        mon_list_res = await loop.run_in_executor(None, lambda: urllib.request.urlopen(f"{base_url}/api/monitors").read())
        mon_list = json.loads(mon_list_res.decode("utf-8"))
        self.assertEqual(len(mon_list), 1)
        self.assertEqual(mon_list[0]["id"], "test_mon_api")

        # 3. Request Status Badge GET /api/badge/test_mon_api
        badge_res = await loop.run_in_executor(None, lambda: urllib.request.urlopen(f"{base_url}/api/badge/test_mon_api").read())
        svg_content = badge_res.decode("utf-8")
        self.assertTrue(svg_content.startswith("<svg"))
        self.assertIn("API Test", svg_content)


if __name__ == "__main__":
    unittest.main()
