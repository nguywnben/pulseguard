"""Data models for PulseGuard."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
import time


class MonitorType(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"
    DNS = "dns"


class MonitorStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    PENDING = "pending"
    PAUSED = "paused"


class IncidentState(str, Enum):
    ONGOING = "ongoing"
    RESOLVED = "resolved"


@dataclass
class Monitor:
    id: str
    name: str
    type: MonitorType
    target: str  # URL or host:port
    interval_seconds: int = 60
    timeout_seconds: int = 10
    expected_status_code: int = 200
    keyword_match: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    http_method: str = "GET"
    http_body: Optional[str] = None
    max_redirects: int = 5
    consecutive_strikes_threshold: int = 2
    alert_channels: List[str] = field(default_factory=list)
    group_name: str = "Default"
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value if isinstance(self.type, MonitorType) else self.type,
            "target": self.target,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "expected_status_code": self.expected_status_code,
            "keyword_match": self.keyword_match,
            "headers": self.headers,
            "http_method": self.http_method,
            "http_body": self.http_body,
            "max_redirects": self.max_redirects,
            "consecutive_strikes_threshold": self.consecutive_strikes_threshold,
            "alert_channels": self.alert_channels,
            "group_name": self.group_name,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Monitor":
        return cls(
            id=data["id"],
            name=data["name"],
            type=MonitorType(data.get("type", "http")),
            target=data["target"],
            interval_seconds=int(data.get("interval_seconds", 60)),
            timeout_seconds=int(data.get("timeout_seconds", 10)),
            expected_status_code=int(data.get("expected_status_code", 200)),
            keyword_match=data.get("keyword_match"),
            headers=data.get("headers") or {},
            http_method=data.get("http_method", "GET"),
            http_body=data.get("http_body"),
            max_redirects=int(data.get("max_redirects", 5)),
            consecutive_strikes_threshold=int(data.get("consecutive_strikes_threshold", 2)),
            alert_channels=data.get("alert_channels") or [],
            group_name=data.get("group_name", "Default"),
            enabled=bool(data.get("enabled", True)),
            created_at=float(data.get("created_at", time.time())),
            description=data.get("description", ""),
        )


@dataclass
class Heartbeat:
    monitor_id: str
    timestamp: float
    is_up: bool
    latency_ms: float
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    cert_days_remaining: Optional[int] = None
    response_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "timestamp": self.timestamp,
            "is_up": self.is_up,
            "latency_ms": round(self.latency_ms, 2),
            "status_code": self.status_code,
            "error_message": self.error_message,
            "cert_days_remaining": self.cert_days_remaining,
            "response_size_bytes": self.response_size_bytes,
        }


@dataclass
class Incident:
    id: str
    monitor_id: str
    started_at: float
    state: IncidentState = IncidentState.ONGOING
    resolved_at: Optional[float] = None
    cause: str = ""
    error_details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        duration_s = None
        if self.resolved_at:
            duration_s = round(self.resolved_at - self.started_at, 1)
        return {
            "id": self.id,
            "monitor_id": self.monitor_id,
            "started_at": self.started_at,
            "state": self.state.value if isinstance(self.state, IncidentState) else self.state,
            "resolved_at": self.resolved_at,
            "duration_seconds": duration_s,
            "cause": self.cause,
            "error_details": self.error_details,
        }
