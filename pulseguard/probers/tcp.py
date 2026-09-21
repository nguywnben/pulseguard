"""Zero-dependency asynchronous TCP port socket prober."""

import asyncio
import time
from ..models import Monitor, Heartbeat


async def probe_tcp(monitor: Monitor) -> Heartbeat:
    """Performs raw TCP 3-way handshake to measure socket availability and latency."""
    # Target format: host:port or ip:port
    target = monitor.target
    if "://" in target:
        target = target.split("://", 1)[1]
    target = target.rstrip("/")

    parts = target.split(":", 1)
    if len(parts) != 2:
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=time.time(),
            is_up=False,
            latency_ms=0.0,
            error_message="Invalid TCP target format. Expected 'hostname:port' or 'ip:port'",
        )

    host = parts[0]
    try:
        port = int(parts[1])
    except ValueError:
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=time.time(),
            is_up=False,
            latency_ms=0.0,
            error_message=f"Invalid TCP port: {parts[1]}",
        )

    start_time = time.perf_counter()
    ts = time.time()

    try:
        connect_coro = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(connect_coro, timeout=monitor.timeout_seconds)
        latency = (time.perf_counter() - start_time) * 1000.0

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=True,
            latency_ms=latency,
            status_code=None,
            error_message=None,
        )
    except asyncio.TimeoutError:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"TCP connection timed out after {monitor.timeout_seconds}s",
        )
    except Exception as e:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"TCP handshake failed: {str(e)[:150]}",
        )
