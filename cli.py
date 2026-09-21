#!/usr/bin/env python3
"""PulseGuard CLI & Daemon Orchestrator."""

import argparse
import asyncio
import sys
import os
import signal
import json
from pulseguard.config import load_config, save_config, DEFAULT_CONFIG
from pulseguard.db import Database
from pulseguard.models import Monitor, MonitorType
from pulseguard.notifier import Notifier
from pulseguard.engine import SentinelEngine
from pulseguard.server import HttpServer


def main():
    parser = argparse.ArgumentParser(
        prog="pulseguard",
        description="PulseGuard: Autonomous Zero-Dependency Uptime & API Sentinel Engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # 1. Start Daemon
    daemon_parser = subparsers.add_parser("start", help="Start PulseGuard 24/7 background sentinel daemon")
    daemon_parser.add_argument("--config", "-c", default="config.json", help="Path to config.json")
    daemon_parser.add_argument("--port", "-p", type=int, default=None, help="Override HTTP server port")

    # 2. Check / Probe Once
    probe_parser = subparsers.add_parser("check", help="Run immediate ad-hoc probe on a target")
    probe_parser.add_argument("target", help="URL or host:port (e.g. https://nguywnben.dev or 1.1.1.1:53)")
    probe_parser.add_argument("--type", "-t", choices=["http", "https", "tcp", "dns"], default="https")

    # 3. List Monitors
    list_parser = subparsers.add_parser("list", help="List all configured monitors and status")
    list_parser.add_argument("--config", "-c", default="config.json")

    # 4. Add Monitor
    add_parser = subparsers.add_parser("add", help="Add a new target monitor")
    add_parser.add_argument("--id", required=True, help="Unique monitor identifier")
    add_parser.add_argument("--name", required=True, help="Human-readable monitor name")
    add_parser.add_argument("--target", required=True, help="Target URL or host:port")
    add_parser.add_argument("--type", choices=["http", "https", "tcp", "dns"], default="https")
    add_parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    add_parser.add_argument("--group", default="Default", help="Group name for dashboard")

    # 5. Export Badges
    badge_parser = subparsers.add_parser("badge", help="Generate SVG badge for a monitor")
    badge_parser.add_argument("monitor_id", help="Monitor identifier")
    badge_parser.add_argument("--output", "-o", default="badge.svg", help="Output file path")

    args = parser.parse_args()

    if not args.command or args.command == "start":
        config_path = getattr(args, "config", "config.json")
        port_override = getattr(args, "port", None)
        run_daemon(config_path, port_override)

    elif args.command == "check":
        run_check(args.target, args.type)

    elif args.command == "list":
        run_list(args.config)

    elif args.command == "add":
        run_add(args)

    elif args.command == "badge":
        run_badge(args.monitor_id, args.output)


def run_daemon(config_path: str, port_override: int = None):
    conf = load_config(config_path)
    if port_override:
        conf["server"]["port"] = port_override

    db_path = conf.get("database", {}).get("path", "pulseguard.db")
    db = Database(db_path)

    # Initialize default monitors if database is empty
    existing = db.list_monitors()
    if not existing:
        print("[PulseGuard] Populating initial monitors from configuration...")
        for m_data in conf.get("default_monitors", []):
            m = Monitor.from_dict(m_data)
            db.upsert_monitor(m)

    notifier = Notifier(conf.get("alerting", {}))
    engine = SentinelEngine(db, notifier)
    server = HttpServer(
        db,
        engine,
        host=conf.get("server", {}).get("host", "0.0.0.0"),
        port=conf.get("server", {}).get("port", 8920),
    )

    async def _async_main():
        await engine.start()
        await server.start()

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

        print(f"[PulseGuard] Daemon initialized successfully. Monitoring {len(db.list_monitors())} targets.")
        await stop_event.wait()

        print("\n[PulseGuard] Shutting down gracefully...")
        await server.stop()
        await engine.stop()

    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass


def run_check(target: str, probe_type: str):
    m = Monitor(
        id="adhoc",
        name="Ad-hoc Probe",
        type=MonitorType(probe_type),
        target=target,
        timeout_seconds=10,
    )

    db = Database(":memory:")
    notifier = Notifier({})
    engine = SentinelEngine(db, notifier)

    async def _do_probe():
        print(f"[*] Probing {probe_type.upper()} target: {target} ...")
        hb = await engine.run_single_probe(m)
        print(f"[+] Status: {'UP (Healthy)' if hb.is_up else 'DOWN (Unhealthy)'}")
        print(f"[+] Latency: {hb.latency_ms:.2f} ms")
        if hb.status_code:
            print(f"[+] HTTP Status: {hb.status_code}")
        if hb.cert_days_remaining is not None:
            print(f"[+] SSL Certificate: {hb.cert_days_remaining} days remaining")
        if hb.error_message:
            print(f"[-] Error: {hb.error_message}")

    asyncio.run(_do_probe())


def run_list(config_path: str):
    conf = load_config(config_path)
    db = Database(conf.get("database", {}).get("path", "pulseguard.db"))
    monitors = db.list_monitors()
    print(f"\n{'ID':<18} | {'NAME':<32} | {'TYPE':<6} | {'STATUS':<8} | {'UPTIME (30D)':<12} | {'LATENCY'}")
    print("-" * 95)
    for m in monitors:
        latest = db.get_latest_heartbeat(m.id)
        stats = db.get_aggregated_stats(m.id)
        status_str = "UP" if (latest and latest.is_up) else ("DOWN" if latest else "PENDING")
        lat_str = f"{latest.latency_ms:.1f} ms" if latest else "--"
        uptime_str = f"{stats.get('uptime_30d', 100):.1f}%"
        print(f"{m.id:<18} | {m.name[:32]:<32} | {m.type.value:<6} | {status_str:<8} | {uptime_str:<12} | {lat_str}")
    print()


def run_add(args):
    db = Database("pulseguard.db")
    m = Monitor(
        id=args.id,
        name=args.name,
        type=MonitorType(args.type),
        target=args.target,
        interval_seconds=args.interval,
        group_name=args.group,
    )
    db.upsert_monitor(m)
    print(f"[+] Monitor '{m.name}' ({m.id}) added successfully.")


def run_badge(monitor_id: str, output_path: str):
    from pulseguard.web.badges import generate_status_badge
    db = Database("pulseguard.db")
    m = db.get_monitor(monitor_id)
    if not m:
        print(f"[-] Monitor '{monitor_id}' not found.")
        sys.exit(1)
    stats = db.get_aggregated_stats(monitor_id)
    svg = generate_status_badge(label=m.name, uptime_pct=stats.get("uptime_30d", 100.0))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[+] Badge saved to {output_path}")


if __name__ == "__main__":
    main()
