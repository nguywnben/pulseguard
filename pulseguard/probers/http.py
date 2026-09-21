"""Zero-dependency asynchronous HTTP/HTTPS prober with SSL Certificate auditing."""

import asyncio
import ssl
import time
import re
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import Tuple, Optional
from ..models import Monitor, Heartbeat


async def probe_http(monitor: Monitor) -> Heartbeat:
    """Performs non-blocking async HTTP/HTTPS probe with custom headers, body assertion, and SSL check."""
    parsed = urlparse(monitor.target)
    is_https = parsed.scheme.lower() == "https"
    port = parsed.port or (443 if is_https else 80)
    hostname = parsed.hostname or "localhost"
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    start_time = time.perf_counter()
    ts = time.time()
    cert_days_remaining: Optional[int] = None

    # Step 1: Check SSL Certificate if HTTPS
    if is_https:
        try:
            cert_days_remaining = await _inspect_ssl_cert_async(hostname, port, monitor.timeout_seconds)
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000.0
            return Heartbeat(
                monitor_id=monitor.id,
                timestamp=ts,
                is_up=False,
                latency_ms=latency,
                error_message=f"SSL/TLS Error: {str(e)[:150]}",
                cert_days_remaining=None,
            )

    # Step 2: Establish connection and send HTTP request
    try:
        ssl_ctx = None
        if is_https:
            ssl_ctx = ssl.create_default_context()
            # Standard verification

        connect_coro = asyncio.open_connection(
            hostname,
            port,
            ssl=ssl_ctx,
            server_hostname=hostname if is_https else None,
        )

        reader, writer = await asyncio.wait_for(connect_coro, timeout=monitor.timeout_seconds)
    except asyncio.TimeoutError:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"Connection timed out ({monitor.timeout_seconds}s)",
            cert_days_remaining=cert_days_remaining,
        )
    except Exception as e:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"Connection failed: {str(e)[:150]}",
            cert_days_remaining=cert_days_remaining,
        )

    # Construct Raw HTTP/1.1 Request
    try:
        method = monitor.http_method.upper()
        headers = {
            "Host": hostname if port in (80, 443) else f"{hostname}:{port}",
            "User-Agent": "PulseGuard-Sentinel/1.0 (+https://github.com/nguywnben)",
            "Accept": "*/*",
            "Connection": "close",
        }
        if monitor.headers:
            headers.update(monitor.headers)

        body_bytes = b""
        if monitor.http_body and method in ("POST", "PUT", "PATCH"):
            body_bytes = monitor.http_body.encode("utf-8")
            headers["Content-Length"] = str(len(body_bytes))

        req_lines = [f"{method} {path} HTTP/1.1"]
        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")
        req_lines.append("")
        req_lines.append("")

        raw_req = "\r\n".join(req_lines).encode("utf-8") + body_bytes

        writer.write(raw_req)
        await writer.drain()

        # Read Response with timeout
        raw_resp = await asyncio.wait_for(
            reader.read(65536),  # read up to 64KB for status and keyword verification
            timeout=monitor.timeout_seconds,
        )

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

        latency = (time.perf_counter() - start_time) * 1000.0

        if not raw_resp:
            return Heartbeat(
                monitor_id=monitor.id,
                timestamp=ts,
                is_up=False,
                latency_ms=latency,
                error_message="Empty response received from server",
                cert_days_remaining=cert_days_remaining,
            )

        status_code, body_text = _parse_http_response(raw_resp)

        # Assert Status Code
        is_up = True
        err_msg = None

        if status_code != monitor.expected_status_code:
            # Special case: allow 2xx if expected 200, or allow redirect if expected
            if not (200 <= status_code < 400 and monitor.expected_status_code == 200):
                is_up = False
                err_msg = f"HTTP {status_code} (expected {monitor.expected_status_code})"

        # Assert Keyword/Regex if configured
        if is_up and monitor.keyword_match:
            if not re.search(monitor.keyword_match, body_text):
                is_up = False
                err_msg = f"Response assertion failed: pattern '{monitor.keyword_match}' not found"

        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=is_up,
            latency_ms=latency,
            status_code=status_code,
            error_message=err_msg,
            cert_days_remaining=cert_days_remaining,
            response_size_bytes=len(raw_resp),
        )

    except asyncio.TimeoutError:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"Read timed out ({monitor.timeout_seconds}s)",
            cert_days_remaining=cert_days_remaining,
        )
    except Exception as e:
        latency = (time.perf_counter() - start_time) * 1000.0
        return Heartbeat(
            monitor_id=monitor.id,
            timestamp=ts,
            is_up=False,
            latency_ms=latency,
            error_message=f"I/O Error: {str(e)[:150]}",
            cert_days_remaining=cert_days_remaining,
        )


def _parse_http_response(raw: bytes) -> Tuple[int, str]:
    """Parses status code and response body text from raw HTTP/1.1 response."""
    parts = raw.split(b"\r\n\r\n", 1)
    header_part = parts[0].decode("latin-1", errors="replace")
    body_part = parts[1].decode("utf-8", errors="replace") if len(parts) > 1 else ""

    status_line = header_part.splitlines()[0] if header_part.splitlines() else ""
    # Format: HTTP/1.1 200 OK
    tokens = status_line.split(" ", 2)
    status_code = 0
    if len(tokens) >= 2 and tokens[1].isdigit():
        status_code = int(tokens[1])

    return status_code, body_part


async def _inspect_ssl_cert_async(hostname: str, port: int, timeout: float) -> Optional[int]:
    """Inspects peer SSL certificate expiration date asynchronously in executor thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_inspect_cert, hostname, port, timeout)


def _sync_inspect_cert(hostname: str, port: int, timeout: float) -> Optional[int]:
    """Retrieves remaining days before SSL certificate expiration."""
    import socket
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert = ssock.getpeercert()
            if not cert or "notAfter" not in cert:
                return None
            expire_str = cert["notAfter"]
            # Ex: 'May 17 08:31:00 2026 GMT'
            expire_dt = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            days_left = (expire_dt - now_dt).days
            return max(0, days_left)
