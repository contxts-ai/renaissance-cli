"""Configuration: CLI flag > env var > config file > default."""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "renaissance"
CONFIG_FILE = CONFIG_DIR / "cli.json"

_DEFAULTS = {
    "trigger_url": "http://localhost:58100",
    "trigger_api_key": "",
    "claude_server_url": "http://localhost:58000",
}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_config()
    existing.update(data)
    CONFIG_FILE.write_text(json.dumps(existing, indent=2) + "\n")


def get(key: str) -> str:
    """Resolve config value: env var > config file > default."""
    env_key = key.upper()
    env_val = os.getenv(env_key, "")
    if env_val:
        return env_val
    file_val = _load_config().get(key, "")
    if file_val:
        return str(file_val)
    return _DEFAULTS.get(key, "")


def get_trigger_url() -> str:
    return get("trigger_url")


def get_trigger_api_key() -> str:
    return get("trigger_api_key")


def get_claude_server_url() -> str:
    return get("claude_server_url")
