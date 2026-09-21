"""Core scheduling engine, worker loop, and incident state-machine."""

import asyncio
import time
import uuid
import logging
from typing import Dict, Optional, Set
from .models import Monitor, Heartbeat, Incident, IncidentState, MonitorStatus
from .db import Database
from .notifier import Notifier
from .probers.http import probe_http
from .probers.tcp import probe_tcp
from .probers.dns import probe_dns

logger = logging.getLogger("PulseGuard.Engine")


class SentinelEngine:
    def __init__(self, db: Database, notifier: Notifier):
        self.db = db
        self.notifier = notifier
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        # Track consecutive failure counts per monitor {monitor_id: count}
        self._consecutive_failures: Dict[str, int] = {}

    async def start(self) -> None:
        """Starts the main scheduling loop."""
        self._running = True
        logger.info("Starting PulseGuard Sentinel Engine...")
        main_task = asyncio.create_task(self._main_scheduler_loop())
        self._tasks.add(main_task)

    async def stop(self) -> None:
        """Stops all background scheduler tasks gracefully."""
        self._running = False
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("PulseGuard Sentinel Engine stopped.")

    async def _main_scheduler_loop(self) -> None:
        """Periodic loop that evaluates which monitors are due for a probe."""
        # Next run timestamps {monitor_id: next_run_ts}
        next_runs: Dict[str, float] = {}

        while self._running:
            try:
                monitors = self.db.list_monitors(enabled_only=True)
                now = time.time()

                for m in monitors:
                    next_run = next_runs.get(m.id, 0.0)
                    if now >= next_run:
                        # Schedule probe task
                        probe_task = asyncio.create_task(self.run_single_probe(m))
                        self._tasks.add(probe_task)
                        probe_task.add_done_callback(self._tasks.discard)
                        next_runs[m.id] = now + m.interval_seconds

                # Clean up monitors that were deleted
                active_ids = {m.id for m in monitors}
                next_runs = {mid: ts for mid, ts in next_runs.items() if mid in active_ids}

                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in scheduler loop: %s", e)
                await asyncio.sleep(2.0)

    async def run_single_probe(self, monitor: Monitor) -> Heartbeat:
        """Executes a probe for a single monitor and updates the incident state-machine."""
        # Protocol dispatch
        m_type = monitor.type.value if hasattr(monitor.type, "value") else str(monitor.type)
        if m_type in ("http", "https"):
            hb = await probe_http(monitor)
        elif m_type == "tcp":
            hb = await probe_tcp(monitor)
        elif m_type == "dns":
            hb = await probe_dns(monitor)
        else:
            hb = Heartbeat(
                monitor_id=monitor.id,
                timestamp=time.time(),
                is_up=False,
                latency_ms=0.0,
                error_message=f"Unsupported monitor protocol: {m_type}",
            )

        # Record to time-series DB
        self.db.record_heartbeat(hb)

        # Update Incident State-Machine
        await self._process_state_transition(monitor, hb)
        return hb

    async def _process_state_transition(self, monitor: Monitor, hb: Heartbeat) -> None:
        """Handles debounce strikes, incident creation, and resolution."""
        ongoing = self.db.get_ongoing_incident(monitor.id)

        if not hb.is_up:
            current_failures = self._consecutive_failures.get(monitor.id, 0) + 1
            self._consecutive_failures[monitor.id] = current_failures

            # Check if threshold reached
            if current_failures >= monitor.consecutive_strikes_threshold:
                if not ongoing:
                    incident_id = f"inc_{uuid.uuid4().hex[:12]}"
                    new_incident = Incident(
                        id=incident_id,
                        monitor_id=monitor.id,
                        started_at=hb.timestamp,
                        state=IncidentState.ONGOING,
                        cause=hb.error_message or "Probe check failed",
                        error_details=f"Consecutive failures: {current_failures}",
                    )
                    self.db.create_incident(new_incident)
                    logger.warning(
                        "Incident TRIGGERED for '%s' (threshold=%d, strikes=%d): %s",
                        monitor.name,
                        monitor.consecutive_strikes_threshold,
                        current_failures,
                        hb.error_message,
                    )
                    # Dispatch notifications
                    await self.notifier.send_incident_alert(monitor, new_incident, hb)
        else:
            # Monitor is UP
            self._consecutive_failures[monitor.id] = 0

            if ongoing:
                self.db.resolve_incident(ongoing.id, hb.timestamp)
                logger.info("Incident RESOLVED for '%s' after downtime.", monitor.name)
                ongoing.resolved_at = hb.timestamp
                await self.notifier.send_recovery_alert(monitor, ongoing, hb)
