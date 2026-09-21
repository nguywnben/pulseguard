"""Tests for Database and Rolling Analytics."""

import unittest
import os
import time
from pulseguard.db import Database
from pulseguard.models import Monitor, Heartbeat, Incident, MonitorType, IncidentState


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.test_db = f"/tmp/test_pulseguard_{int(time.time() * 1000)}.db"
        self.db = Database(self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        if os.path.exists(f"{self.test_db}-wal"):
            os.remove(f"{self.test_db}-wal")
        if os.path.exists(f"{self.test_db}-shm"):
            os.remove(f"{self.test_db}-shm")

    def test_upsert_and_get_monitor(self):
        m = Monitor(
            id="test_site",
            name="Test Website",
            type=MonitorType.HTTPS,
            target="https://example.com",
            interval_seconds=30,
        )
        self.db.upsert_monitor(m)
        fetched = self.db.get_monitor("test_site")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Test Website")
        self.assertEqual(fetched.interval_seconds, 30)

    def test_record_heartbeat_and_stats(self):
        m = Monitor(
            id="test_site",
            name="Test Website",
            type=MonitorType.HTTPS,
            target="https://example.com",
        )
        self.db.upsert_monitor(m)

        now = time.time()
        # Record 4 successful heartbeats and 1 failed
        for i in range(4):
            self.db.record_heartbeat(
                Heartbeat(
                    monitor_id="test_site",
                    timestamp=now - (i * 60),
                    is_up=True,
                    latency_ms=25.0 + i,
                )
            )
        self.db.record_heartbeat(
            Heartbeat(
                monitor_id="test_site",
                timestamp=now - 300,
                is_up=False,
                latency_ms=1000.0,
                error_message="Timed out",
            )
        )

        latest = self.db.get_latest_heartbeat("test_site")
        self.assertTrue(latest.is_up)

        stats = self.db.get_aggregated_stats("test_site")
        # 4 up out of 5 = 80.0%
        self.assertEqual(stats["uptime_24h"], 80.0)
        self.assertIn("daily_bars", stats)
        self.assertEqual(len(stats["daily_bars"]), 60)

    def test_incident_lifecycle(self):
        m = Monitor(id="site_a", name="A", type=MonitorType.HTTP, target="http://a.com")
        self.db.upsert_monitor(m)

        inc = Incident(
            id="inc_1",
            monitor_id="site_a",
            started_at=time.time() - 60,
            state=IncidentState.ONGOING,
            cause="500 Internal Server Error",
        )
        self.db.create_incident(inc)

        active = self.db.get_ongoing_incident("site_a")
        self.assertIsNotNone(active)
        self.assertEqual(active.id, "inc_1")

        # Resolve
        now = time.time()
        self.db.resolve_incident("inc_1", now)
        active_after = self.db.get_ongoing_incident("site_a")
        self.assertIsNone(active_after)


if __name__ == "__main__":
    unittest.main()
