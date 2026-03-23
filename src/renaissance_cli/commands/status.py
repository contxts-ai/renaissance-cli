"""ren status — system health check."""

from __future__ import annotations

import typer

import os

from renaissance_cli._client import api_get
from renaissance_cli._output import OutputFormat, OutputOpt, QuietOpt, ok, setup


def status(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Check Trigger API and system health.

    Returns connectivity status for Trigger API, Temporal, and Claude Server.
    Use --output json for structured result.
    """
    setup(output, quiet)
    trigger_url = os.getenv("TRIGGER_URL", "http://localhost:58100")
    data = api_get("/health")
    ok(
        result={"trigger_url": trigger_url, **data},
        next_actions=[
            {"command": "ren pipeline list", "description": "List running pipelines"},
            {"command": "ren schedule list", "description": "List schedules"},
            {"command": "ren template list", "description": "List available templates"},
        ],
        human_text=f"Trigger API ({trigger_url}): healthy",
    )
