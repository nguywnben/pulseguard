"""Tests for HTTP, TCP, and DNS probers."""

import unittest
import asyncio
from pulseguard.models import Monitor, MonitorType
from pulseguard.probers.http import probe_http
from pulseguard.probers.tcp import probe_tcp
from pulseguard.probers.dns import probe_dns


class TestProbers(unittest.IsolatedAsyncioTestCase):
    async def test_dns_prober_valid(self):
        m = Monitor(
            id="dns_test",
            name="Google DNS",
            type=MonitorType.DNS,
            target="google.com",
            timeout_seconds=5,
        )
        hb = await probe_dns(m)
        self.assertTrue(hb.is_up)
        self.assertGreater(hb.latency_ms, 0)
        self.assertIsNone(hb.error_message)

    async def test_dns_prober_invalid(self):
        m = Monitor(
            id="dns_invalid",
            name="Invalid DNS",
            type=MonitorType.DNS,
            target="this-domain-surely-does-not-exist-xyz999.invalid",
            timeout_seconds=2,
        )
        hb = await probe_dns(m)
        self.assertFalse(hb.is_up)
        self.assertIsNotNone(hb.error_message)

    async def test_tcp_prober_valid(self):
        # Cloudflare DNS port 53 (TCP)
        m = Monitor(
            id="tcp_test",
            name="Cloudflare DNS TCP",
            type=MonitorType.TCP,
            target="1.1.1.1:53",
            timeout_seconds=5,
        )
        hb = await probe_tcp(m)
        self.assertTrue(hb.is_up)
        self.assertGreater(hb.latency_ms, 0)

    async def test_tcp_prober_closed_port(self):
        # Localhost unused port
        m = Monitor(
            id="tcp_closed",
            name="Closed Port",
            type=MonitorType.TCP,
            target="127.0.0.1:49151",
            timeout_seconds=1,
        )
        hb = await probe_tcp(m)
        self.assertFalse(hb.is_up)

    async def test_http_prober_live(self):
        m = Monitor(
            id="http_test",
            name="Cloudflare 1.1.1.1 HTTPS",
            type=MonitorType.HTTPS,
            target="https://1.1.1.1",
            timeout_seconds=5,
            expected_status_code=200,
        )
        hb = await probe_http(m)
        self.assertTrue(hb.is_up)
        self.assertIsNotNone(hb.cert_days_remaining)
        self.assertGreater(hb.cert_days_remaining, 0)


if __name__ == "__main__":
    unittest.main()
