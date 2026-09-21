"""Tests for Sentinel Engine and State-Machine Transitions."""

import unittest
import os
import time
from pulseguard.db import Database
from pulseguard.models import Monitor, MonitorType
from pulseguard.notifier import Notifier
from pulseguard.engine import SentinelEngine


class TestEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_db = f"/tmp/test_engine_{int(time.time() * 1000)}.db"
        self.db = Database(self.test_db)
        self.notifier = Notifier({})
        self.engine = SentinelEngine(self.db, self.notifier)

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    async def test_strike_threshold_state_machine(self):
        # Target that will fail
        m = Monitor(
            id="failing_target",
            name="Failing Server",
            type=MonitorType.TCP,
            target="127.0.0.1:49999",
            timeout_seconds=1,
            consecutive_strikes_threshold=2,
        )
        self.db.upsert_monitor(m)

        # First failure strike (strikes = 1) -> No incident yet
        hb1 = await self.engine.run_single_probe(m)
        self.assertFalse(hb1.is_up)
        self.assertIsNone(self.db.get_ongoing_incident(m.id))

        # Second failure strike (strikes = 2) -> Incident TRIGGERED
        hb2 = await self.engine.run_single_probe(m)
        self.assertFalse(hb2.is_up)
        inc = self.db.get_ongoing_incident(m.id)
        self.assertIsNotNone(inc)
        self.assertEqual(inc.monitor_id, m.id)

        # Change monitor target to healthy
        m.target = "1.1.1.1:53"
        self.db.upsert_monitor(m)

        # Probing again -> UP -> Incident RESOLVED
        hb3 = await self.engine.run_single_probe(m)
        self.assertTrue(hb3.is_up)
        self.assertIsNone(self.db.get_ongoing_incident(m.id))


if __name__ == "__main__":
    unittest.main()
