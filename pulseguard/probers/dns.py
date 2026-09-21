"""Zero-dependency asynchronous DNS resolution prober."""

import asyncio
import time
import socket
from ..models import Monitor, Heartbeat


async def probe_dns(monitor: Monitor) -> Heartbeat:
    """Measures DNS lookup resolution time and IP reachability."""
    target = monitor.target.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0]
    start_time = time.perf_counter()
    ts = time.time()

    loop = asyncio.get_running_loop()
    try:
        # Resolve address asynchronously via thread pool
        addrinfo = await asyncio.wait_for(
            loop.getaddrinfo(target, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM),
            timeout=monitor.timeout_seconds,
        )
        latency = (time.perf_counter() - start_time) * 1000.0

        if not addrinfo:
            return Heartbeat(
                monitor_id=monitor.id,
                timestamp=ts,
                is_up=False,
                latency_ms=latency,
                error_message="DNS returned no address records",
            )

        resolved_ips = list({res[4][0] for res in addrinfo})
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=True,
            latency_ms=latency,
            error_message=None,
            response_size_bytes=len(", ".join(resolved_ips)),
        )
    except asyncio.TimeoutError:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"DNS resolution timed out after {monitor.timeout_seconds}s",
        )
    except Exception as e:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"DNS lookup failed: {str(e)[:150]}",
        )
