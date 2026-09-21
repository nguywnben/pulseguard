# 🛡️ PulseGuard — Autonomous Zero-Dependency Uptime & API Sentinel Engine

[![Uptime](https://img.shields.io/badge/Uptime-100.00%25-brightgreen)](http://217.216.74.251:8920/)
[![Status](https://img.shields.io/badge/Status-Operational-brightgreen)](http://217.216.74.251:8920/)
[![Architecture](https://img.shields.io/badge/Architecture-Zero--Dependency-blue)](SPEC.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

**PulseGuard** is an industrial-grade, ultra-lightweight, zero-dependency asynchronous uptime monitoring and API reliability sentinel engine.
Engineered with pure Python 3 standard library (`asyncio`, `ssl`, `sqlite3`, `urllib`), PulseGuard starts in **under 20ms**, consumes **<25MB RAM**, and runs autonomously **24/7** without requiring any `pip` dependencies or external database servers.

---

## 🌟 Key Architecture & Capabilities

* **Zero External Dependencies:** Built with pure asynchronous Python 3.12 (standard library only). No wheel compiling, no pip headaches, instant deployment on any server/container.
* **Multi-Protocol Active Probing:**
  * **HTTP/HTTPS:** Assert custom status codes, verify response headers/body regex, and audit SSL/TLS certificates with countdown warnings.
  * **TCP Handshake:** Low-latency socket checks for databases (PostgreSQL, MySQL, Redis), SSH (port 22), mail servers.
  * **DNS Latency:** Domain name resolution time and record verification.
* **Persistent Time-Series Storage:** High-performance SQLite engine operating in **WAL mode** (`Write-Ahead Logging`) with rolling 60-day visual uptime status bars and automated data pruning.
* **Intelligent Incident State-Machine:** Debounce thresholds (consecutive failure strikes) to eliminate transient blips; tracks exact outage duration and postmortems.
* **Omnichannel Incident Alerting:** Instant push notifications via Telegram Bot, Discord Webhooks, Slack Webhooks, and NTFY.sh.
* **Self-Hosted Dark/Light Status Page:** Built-in responsive HTML5/CSS3 status dashboard running on an embedded async HTTP server (`http://localhost:8920`).
* **Dynamic SVG Status Badges:** Generate real-time SVG badges for GitHub profile READMEs or documentation (e.g. `GET /api/badge/{monitor_id}`).
* **Full RESTful Management API & CLI:** Complete headless control via `pulseguard` command line.

---

## 🚀 Quick Start

### 1. Run Ad-hoc Health Check
```bash
./cli.py check https://nguywnben.dev
./cli.py check 1.1.1.1:53 --type tcp
```

### 2. Start Background Daemon (24/7)
```bash
./cli.py start
```
The status page and REST API will immediately be live at: **`http://localhost:8920`**.

### 3. CLI Management Commands
```bash
# List all active monitors with live status and 30-day uptime
./cli.py list

# Add a new monitor target
./cli.py add --id yuzu_api --name "Yuzu Streaming Engine" --target "https://api.yuzu.dev" --type https --interval 30

# Export live SVG badge to disk
./cli.py badge nguywnben_dev -o badge.svg
```

---

## 📡 REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `GET /` | `GET` | Self-hosted Web Status Dashboard |
| `GET /api/status` | `GET` | Snapshot of all monitors, overall health, 60-day bars & incidents |
| `GET /api/monitors` | `GET` | List all configured monitor definitions |
| `POST /api/monitors` | `POST` | Create or update a monitor target dynamically |
| `DELETE /api/monitors/{id}` | `DELETE` | Remove a monitor target |
| `POST /api/monitors/{id}/probe` | `POST` | Trigger an immediate manual probe |
| `GET /api/badge/{id}` | `GET` | Dynamic SVG status badge for GitHub READMEs |
| `GET /healthz` | `GET` | PulseGuard daemon internal healthcheck |

---

## ⚙️ Configuration (`config.json`)
```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8920
  },
  "database": {
    "path": "pulseguard.db",
    "retention_days": 90
  },
  "alerting": {
    "ntfy": {
      "server": "https://ntfy.sh",
      "topic": "pulseguard_ben_alerts"
    }
  }
}
```

---

## 🛡️ Production Deployment (Systemd)

```bash
cp pulseguard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pulseguard
systemctl status pulseguard
```

---

## 📄 License
MIT License &copy; 2026 **Nguyen Cong Ben** (`nguywnben`). All rights reserved.
