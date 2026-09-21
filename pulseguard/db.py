"""SQLite WAL-mode persistence and rolling analytics repository."""

import sqlite3
import json
import time
from typing import List, Optional, Dict, Any
from .models import Monitor, Heartbeat, Incident, IncidentState, MonitorType


class Database:
    def __init__(self, db_path: str = "pulseguard.db"):
        self.db_path = db_path
        self._shared_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", timeout=15.0)
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL DEFAULT 60,
                    timeout_seconds INTEGER NOT NULL DEFAULT 10,
                    expected_status_code INTEGER NOT NULL DEFAULT 200,
                    keyword_match TEXT,
                    headers_json TEXT NOT NULL DEFAULT '{}',
                    http_method TEXT NOT NULL DEFAULT 'GET',
                    http_body TEXT,
                    max_redirects INTEGER NOT NULL DEFAULT 5,
                    consecutive_strikes_threshold INTEGER NOT NULL DEFAULT 2,
                    alert_channels_json TEXT NOT NULL DEFAULT '[]',
                    group_name TEXT NOT NULL DEFAULT 'Default',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS heartbeats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    is_up INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    status_code INTEGER,
                    error_message TEXT,
                    cert_days_remaining INTEGER,
                    response_size_bytes INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_heartbeats_mon_ts 
                ON heartbeats(monitor_id, timestamp DESC);

                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    state TEXT NOT NULL DEFAULT 'ongoing',
                    resolved_at REAL,
                    cause TEXT NOT NULL DEFAULT '',
                    error_details TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_incidents_mon_state 
                ON incidents(monitor_id, state);

                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                """
            )

    # ---------------- Monitor Operations ---------------- #

    def upsert_monitor(self, monitor: Monitor) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO monitors (
                    id, name, type, target, interval_seconds, timeout_seconds,
                    expected_status_code, keyword_match, headers_json, http_method,
                    http_body, max_redirects, consecutive_strikes_threshold,
                    alert_channels_json, group_name, enabled, created_at, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    target=excluded.target,
                    interval_seconds=excluded.interval_seconds,
                    timeout_seconds=excluded.timeout_seconds,
                    expected_status_code=excluded.expected_status_code,
                    keyword_match=excluded.keyword_match,
                    headers_json=excluded.headers_json,
                    http_method=excluded.http_method,
                    http_body=excluded.http_body,
                    max_redirects=excluded.max_redirects,
                    consecutive_strikes_threshold=excluded.consecutive_strikes_threshold,
                    alert_channels_json=excluded.alert_channels_json,
                    group_name=excluded.group_name,
                    enabled=excluded.enabled,
                    description=excluded.description
                """,
                (
                    monitor.id,
                    monitor.name,
                    monitor.type.value if isinstance(monitor.type, MonitorType) else monitor.type,
                    monitor.target,
                    monitor.interval_seconds,
                    monitor.timeout_seconds,
                    monitor.expected_status_code,
                    monitor.keyword_match,
                    json.dumps(monitor.headers),
                    monitor.http_method,
                    monitor.http_body,
                    monitor.max_redirects,
                    monitor.consecutive_strikes_threshold,
                    json.dumps(monitor.alert_channels),
                    monitor.group_name,
                    1 if monitor.enabled else 0,
                    monitor.created_at,
                    monitor.description,
                ),
            )

    def get_monitor(self, monitor_id: str) -> Optional[Monitor]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
            if not row:
                return None
            return self._row_to_monitor(row)

    def list_monitors(self, enabled_only: bool = False) -> List[Monitor]:
        with self._get_conn() as conn:
            query = "SELECT * FROM monitors"
            if enabled_only:
                query += " WHERE enabled = 1"
            query += " ORDER BY group_name, name"
            rows = conn.execute(query).fetchall()
            return [self._row_to_monitor(r) for r in rows]

    def delete_monitor(self, monitor_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
            return cur.rowcount > 0

    def _row_to_monitor(self, row: sqlite3.Row) -> Monitor:
        return Monitor(
            id=row["id"],
            name=row["name"],
            type=MonitorType(row["type"]),
            target=row["target"],
            interval_seconds=row["interval_seconds"],
            timeout_seconds=row["timeout_seconds"],
            expected_status_code=row["expected_status_code"],
            keyword_match=row["keyword_match"],
            headers=json.loads(row["headers_json"] or "{}"),
            http_method=row["http_method"],
            http_body=row["http_body"],
            max_redirects=row["max_redirects"],
            consecutive_strikes_threshold=row["consecutive_strikes_threshold"],
            alert_channels=json.loads(row["alert_channels_json"] or "[]"),
            group_name=row["group_name"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            description=row["description"],
        )

    # ---------------- Heartbeat & Metrics Operations ---------------- #

    def record_heartbeat(self, hb: Heartbeat) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO heartbeats (
                    monitor_id, timestamp, is_up, latency_ms,
                    status_code, error_message, cert_days_remaining,
                    response_size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hb.monitor_id,
                    hb.timestamp,
                    1 if hb.is_up else 0,
                    hb.latency_ms,
                    hb.status_code,
                    hb.error_message,
                    hb.cert_days_remaining,
                    hb.response_size_bytes,
                ),
            )

    def get_latest_heartbeat(self, monitor_id: str) -> Optional[Heartbeat]:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM heartbeats 
                WHERE monitor_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
                """,
                (monitor_id,),
            ).fetchone()
            if not row:
                return None
            return Heartbeat(
                monitor_id=row["monitor_id"],
                timestamp=row["timestamp"],
                is_up=bool(row["is_up"]),
                latency_ms=row["latency_ms"],
                status_code=row["status_code"],
                error_message=row["error_message"],
                cert_days_remaining=row["cert_days_remaining"],
                response_size_bytes=row["response_size_bytes"],
            )

    def get_heartbeats_window(self, monitor_id: str, since_timestamp: float) -> List[Heartbeat]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM heartbeats 
                WHERE monitor_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (monitor_id, since_timestamp),
            ).fetchall()
            return [
                Heartbeat(
                    monitor_id=r["monitor_id"],
                    timestamp=r["timestamp"],
                    is_up=bool(r["is_up"]),
                    latency_ms=r["latency_ms"],
                    status_code=r["status_code"],
                    error_message=r["error_message"],
                    cert_days_remaining=r["cert_days_remaining"],
                    response_size_bytes=r["response_size_bytes"],
                )
                for r in rows
            ]

    def get_aggregated_stats(self, monitor_id: str) -> Dict[str, Any]:
        """Calculates 24h, 7d, 30d uptime percentages and avg/p95 latency."""
        now = time.time()
        windows = {
            "24h": now - 86400,
            "7d": now - (86400 * 7),
            "30d": now - (86400 * 30),
        }
        res: Dict[str, Any] = {}
        with self._get_conn() as conn:
            for label, since in windows.items():
                row = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_up = 1 THEN 1 ELSE 0 END) as up_count,
                        AVG(latency_ms) as avg_latency
                    FROM heartbeats
                    WHERE monitor_id = ? AND timestamp >= ?
                    """,
                    (monitor_id, since),
                ).fetchone()

                total = row["total"] or 0
                up_count = row["up_count"] or 0
                avg_lat = round(row["avg_latency"] or 0.0, 1)

                uptime_pct = 100.0 if total == 0 else round((up_count / total) * 100.0, 2)
                res[f"uptime_{label}"] = uptime_pct
                if label == "24h":
                    res["avg_latency_24h"] = avg_lat

            # Calculate 90 days daily bar status (or 60 bars for clean UI)
            bars = self._get_daily_uptime_bars(conn, monitor_id, days=60)
            res["daily_bars"] = bars

        return res

    def _get_daily_uptime_bars(self, conn: sqlite3.Connection, monitor_id: str, days: int = 60) -> List[Dict[str, Any]]:
        """Returns per-day status for UI uptime block graph."""
        now = time.time()
        start_ts = now - (days * 86400)
        rows = conn.execute(
            """
            SELECT 
                CAST((timestamp - ?) / 86400 AS INTEGER) as day_idx,
                COUNT(*) as total,
                SUM(CASE WHEN is_up = 1 THEN 1 ELSE 0 END) as up_count,
                AVG(latency_ms) as avg_latency
            FROM heartbeats
            WHERE monitor_id = ? AND timestamp >= ?
            GROUP BY day_idx
            ORDER BY day_idx ASC
            """,
            (start_ts, monitor_id, start_ts),
        ).fetchall()

        stats_by_day = {r["day_idx"]: r for r in rows}
        bars = []
        for i in range(days):
            day_time = start_ts + (i * 86400)
            if i in stats_by_day:
                row = stats_by_day[i]
                total = row["total"]
                up = row["up_count"]
                pct = round((up / total) * 100, 1) if total > 0 else 100.0
                status = "up" if pct >= 99.0 else ("degraded" if pct >= 85.0 else "down")
                bars.append({
                    "date": time.strftime("%Y-%m-%d", time.gmtime(day_time)),
                    "uptime_pct": pct,
                    "status": status,
                    "total_checks": total,
                    "avg_latency": round(row["avg_latency"] or 0.0, 1),
                })
            else:
                bars.append({
                    "date": time.strftime("%Y-%m-%d", time.gmtime(day_time)),
                    "uptime_pct": None,
                    "status": "none",
                    "total_checks": 0,
                    "avg_latency": 0,
                })
        return bars

    def prune_old_heartbeats(self, retention_days: int = 90) -> int:
        cutoff = time.time() - (retention_days * 86400)
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM heartbeats WHERE timestamp < ?", (cutoff,))
            return cur.rowcount

    # ---------------- Incident Lifecycle ---------------- #

    def create_incident(self, incident: Incident) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO incidents (id, monitor_id, started_at, state, cause, error_details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.id,
                    incident.monitor_id,
                    incident.started_at,
                    incident.state.value if isinstance(incident.state, IncidentState) else incident.state,
                    incident.cause,
                    incident.error_details,
                ),
            )

    def resolve_incident(self, incident_id: str, resolved_at: float) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE incidents 
                SET state = 'resolved', resolved_at = ?
                WHERE id = ?
                """,
                (resolved_at, incident_id),
            )

    def get_ongoing_incident(self, monitor_id: str) -> Optional[Incident]:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM incidents 
                WHERE monitor_id = ? AND state = 'ongoing'
                ORDER BY started_at DESC LIMIT 1
                """,
                (monitor_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def list_incidents(self, limit: int = 50) -> List[Incident]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM incidents 
                ORDER BY started_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._row_to_incident(r) for r in rows]

    def _row_to_incident(self, row: sqlite3.Row) -> Incident:
        return Incident(
            id=row["id"],
            monitor_id=row["monitor_id"],
            started_at=row["started_at"],
            state=IncidentState(row["state"]),
            resolved_at=row["resolved_at"],
            cause=row["cause"],
            error_details=row["error_details"],
        )
