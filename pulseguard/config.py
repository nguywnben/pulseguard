"""Configuration manager for PulseGuard."""

import json
import os
from typing import Dict, Any

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8920,
    },
    "database": {
        "path": "pulseguard.db",
        "retention_days": 90,
    },
    "alerting": {
        "telegram": {
            "bot_token": "",
            "chat_id": "",
        },
        "discord": {
            "webhook_url": "",
        },
        "slack": {
            "webhook_url": "",
        },
        "ntfy": {
            "server": "https://ntfy.sh",
            "topic": "pulseguard_ben_alerts",
        },
    },
    "default_monitors": [
        {
            "id": "nguywnben_dev",
            "name": "nguywnben.dev (Production)",
            "type": "https",
            "target": "https://nguywnben.dev",
            "interval_seconds": 30,
            "timeout_seconds": 10,
            "expected_status_code": 200,
            "group_name": "Websites & Portfolios",
            "consecutive_strikes_threshold": 2,
            "alert_channels": ["ntfy"],
        },
        {
            "id": "github_profile",
            "name": "GitHub Profile (nguywnben)",
            "type": "https",
            "target": "https://github.com/nguywnben",
            "interval_seconds": 60,
            "timeout_seconds": 10,
            "expected_status_code": 200,
            "group_name": "Public Profiles",
            "consecutive_strikes_threshold": 2,
            "alert_channels": ["ntfy"],
        },
        {
            "id": "cloudflare_dns",
            "name": "Cloudflare Primary DNS (1.1.1.1)",
            "type": "tcp",
            "target": "1.1.1.1:53",
            "interval_seconds": 30,
            "timeout_seconds": 5,
            "group_name": "Infrastructure & Networking",
            "consecutive_strikes_threshold": 2,
            "alert_channels": ["ntfy"],
        },
        {
            "id": "google_dns",
            "name": "Google DNS Resolution (google.com)",
            "type": "dns",
            "target": "google.com",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "group_name": "Infrastructure & Networking",
            "consecutive_strikes_threshold": 2,
            "alert_channels": ["ntfy"],
        },
    ],
}


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_conf = json.load(f)
                conf = DEFAULT_CONFIG.copy()
                conf.update(user_conf)
                return conf
        except Exception as e:
            print(f"[PulseGuard] Warning: Failed to parse {config_path}: {e}. Using defaults.")
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any], config_path: str = "config.json") -> None:
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
