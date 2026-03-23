"""ren doctor — comprehensive platform diagnostic report."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from renaissance_cli._client import api_get
from renaissance_cli._config import get_claude_server_url, get_trigger_url
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    ok,
    setup,
)


def doctor(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Run a comprehensive platform diagnostic.

    Checks service health, local configuration, and connectivity.
    Suggests fixes for any issues found.
    """
    setup(output, quiet)

    issues: list[str] = []
    na: list[dict] = []

    # 1. Local config check
    config_path = Path.home() / ".config" / "renaissance" / "cli.json"
    config_exists = config_path.exists()
    if not config_exists:
        issues.append("No config file (~/.config/renaissance/cli.json)")
        na.append({"command": "ren auth login --key <KEY>", "description": "Configure credentials"})

    trigger_url = get_trigger_url()
    claude_url = get_claude_server_url()

    # 2. Service health (via control plane)
    service_data: dict = {}
    try:
        service_data = api_get("/control-plane/health")
    except SystemExit:
        issues.append(f"Cannot reach Trigger API at {trigger_url}")
        na.append({"command": f"ren auth login --trigger-url <URL>", "description": "Fix Trigger URL"})

    services = service_data.get("services", [])
    overall = service_data.get("overall_status", "unreachable")
    service_issues = service_data.get("issues", [])
    issues.extend(service_issues)

    # 3. CLI version
    from renaissance_cli import __version__

    # Build report
    lines = [
        "Renaissance CLI Diagnostic Report",
        "=" * 40,
        "",
        f"CLI version:  {__version__}",
        f"Trigger URL:  {trigger_url}",
        f"Claude URL:   {claude_url}",
        f"Config file:  {'found' if config_exists else 'MISSING'}",
        "",
        f"Platform health: {overall}",
    ]

    for s in services:
        name = s.get("name", "?")
        status = s.get("status", "?")
        latency = s.get("latency_ms", "?")
        icon = "+" if status == "healthy" else "-" if status in ("degraded", "unreachable") else "?"
        lines.append(f"  [{icon}] {name:<20s} {status:<15s} {latency}ms")

    if issues:
        lines.append("")
        lines.append(f"Issues ({len(issues)}):")
        for issue in issues:
            lines.append(f"  ! {issue}")
    else:
        lines.append("")
        lines.append("No issues found.")

    if not na:
        na.append({"command": "ren capability list", "description": "Explore capabilities"})
        na.append({"command": "ren pipeline list", "description": "List pipelines"})

    result = {
        "version": __version__,
        "trigger_url": trigger_url,
        "claude_server_url": claude_url,
        "config_exists": config_exists,
        "overall_status": overall,
        "services": services,
        "issues": issues,
    }

    ok(result=result, next_actions=na, human_text="\n".join(lines))
