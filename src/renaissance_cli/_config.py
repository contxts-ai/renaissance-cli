"""Environment-based configuration."""

from __future__ import annotations

import os

TRIGGER_URL: str = os.getenv("TRIGGER_URL", "http://localhost:58100")
TRIGGER_API_KEY: str = os.getenv("TRIGGER_API_KEY", "")
