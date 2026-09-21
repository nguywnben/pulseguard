# SPECIFICATION: PulseGuard (Autonomous Zero-Dependency Uptime & API Sentinel Engine)

## 1. Executive Summary & Objective
**PulseGuard** is an industrial-grade, self-contained, zero-dependency async uptime monitoring and API reliability sentinel built for modern developers and autonomous infrastructure.
It runs 24/7 as an ultra-lightweight daemon that performs:
1. Multi-protocol active probing (HTTP/HTTPS with status/regex matching, TLS/SSL Certificate expiration countdown, TCP port handshake, DNS resolution latency, and JSON REST API response assertion).
2. Rolling time-series health metrics stored in atomic SQLite WAL mode (p50, p95, p99 latencies, uptime percentages 24h/7d/30d, incident timelines).
3. Built-in responsive, monochromatic Dark/Light Status Page (self-hosted directly on the daemon or embeddable) providing real-time SVG status badges, incident postmortems, and live health metrics.
4. Intelligent incident lifecycle engine (State machine: `HEALTHY` -> `DEGRADED` -> `DOWN` -> `RECOVERED`) with configurable consecutive strike thresholds, debounce windows, and multi-channel alerting (Telegram Bot, Discord Webhook, Slack, Generic Webhook, and NTFY.sh push notifications).
5. Fast RESTful Management API & CLI tool (`pulseguard-cli`) for full headless orchestration, dynamic monitor onboarding, ad-hoc probe execution, and config export/import.
6. Zero external C-bindings: Pure asynchronous Python 3.12 (standard library only: `asyncio`, `urllib`, `ssl`, `sqlite3`, `json`, `http.server` async engine) - zero bloat, starts in 20ms, consumes <25MB RAM, runs anywhere without pip installation headaches.

---

## 2. Business Logic & Architecture

```
                                  +---------------------------------------+
                                  |         PULSEGUARD CORE DAEMON        |
                                  +---------------------------------------+
                                                     |
             +-----------------------+---------------+-----------------------+
             |                       |                                       |
             v                       v                                       v
   +-------------------+   +--------------------+                 +---------------------+
   |  Async Scheduler  |   | Storage & Metrics  |                 | REST API & UI Host  |
   |  (Priority Queue) |   | (SQLite WAL Mode)  |                 | (Async HTTP Server) |
   +-------------------+   +--------------------+                 +---------------------+
             |                       |                                       |
    [Workers / Probes]       [Incident Engine]                      [Status Page & API]
             |                       |                                       |
    +--------+--------+      +-------+-------+                      +--------+--------+
    |        |        |      |               |                      |        |        |
   HTTP     TCP      TLS  Telegram        Webhooks                HTML5    JSON     SVG
  Assert   Port    Expiry  Alert           Dispatch                Status    API    Badges
```

### 2.1 Probing Protocols
- **HTTP/HTTPS Prober:**
  - Method: GET, HEAD, POST with custom body & headers.
  - Assertions: Expected status code (e.g. 200, 201), max latency threshold, response body regex/substring match.
  - SSL/TLS: Automatic certificate inspection, days-until-expiration calculation, warning triggers when cert expires in < 14 days.
- **TCP Socket Prober:**
  - Tests socket handshake latency for databases, SSH, Redis, Mail servers.
- **DNS Prober:**
  - Verifies domain resolution time and record matching.

### 2.2 Storage & Time-Series Engine (`pulseguard.db`)
- SQLite with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`.
- Tables:
  - `monitors`: Configuration, target, interval, timeout, strike threshold, alert config.
  - `heartbeats`: Time-series probe results (timestamp, latency_ms, status_code, is_up, error_msg, cert_days_left).
  - `incidents`: Event log tracking `start_time`, `end_time`, `state` (down/degraded/recovered), `reason`, `acknowledged`.
  - `maintenance_windows`: Scheduled downtime suppression.

### 2.3 Alerting & Notification Dispatcher
- Multi-tier alert debounce: Only alert after `N` consecutive failures (default: 2 strikes) to eliminate transient network blips.
- Automatic recovery notification when monitor returns to green.
- Templates formatted for Telegram (HTML), Discord/Slack (rich embed markdown), NTFY (instant mobile push).

### 2.4 Built-in Web Server & Dynamic Status Page
- Lightweight embedded async HTTP server running on user-configurable port (default: `8920`).
- Clean monochromatic interface designed in line with `nguywnben.dev` design aesthetics.
- Real-time endpoints:
  - `GET /`: Modern responsive web dashboard (Uptime graph, 90-day bars, operational status, latency charts).
  - `GET /api/status`: Complete JSON snapshot of all monitors, current status, 24h/7d/30d uptime %.
  - `GET /api/monitors`: CRUD monitor management.
  - `POST /api/monitors`: Add/update targets.
  - `GET /api/badge/{monitor_id}`: Dynamic SVG status badge (for GitHub READMEs like `[Uptime 99.98%]` or `[Status UP]`).
  - `GET /healthz`: Healthcheck of PulseGuard itself.

---

## 3. Directory Layout
```
/root/pulseguard/
├── pulseguard/
│   ├── __init__.py
│   ├── config.py           # Configuration parser & defaults (JSON/YAML)
│   ├── db.py               # SQLite WAL repository & metric aggregations
│   ├── models.py           # Core dataclasses (Monitor, Heartbeat, Incident)
│   ├── probers/
│   │   ├── __init__.py
│   │   ├── http.py         # Async HTTP/HTTPS + SSL cert validation
│   │   ├── tcp.py          # Async TCP socket probe
│   │   └── dns.py          # Async DNS resolution probe
│   ├── engine.py           # Core loop, worker pool, incident state-machine
│   ├── notifier.py         # Multi-channel notification dispatcher
│   ├── server.py           # High-performance async HTTP server (API + Web UI)
│   └── web/
│       ├── index.html      # Responsive Dark/Light Status Page (vanilla JS/CSS)
│       └── badges.py       # Pixel-perfect dynamic SVG generator
├── tests/
│   ├── test_db.py
│   ├── test_probers.py
│   ├── test_engine.py
│   ├── test_server.py
│   └── test_notifier.py
├── cli.py                  # PulseGuard CLI runner & manager
├── pulseguard.service      # Systemd service unit definition
└── README.md               # Complete documentation, architecture & usage
```
