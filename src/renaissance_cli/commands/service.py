"""ren service — view platform service health and status."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_get
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    ok,
    setup,
)

service_app = typer.Typer(
    name="service",
    help="View platform service health and status.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@service_app.command("list")
def service_list(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List all platform services with live health status.

    Fan-out health checks to Trigger API, Temporal, Claude Server, etc.
    Returns per-service status, latency, and URL.
    Requires: Trigger API authentication.
    """
    setup(output, quiet)
    data = api_get("/control-plane/services")
    services = data.get("services", [])
    issues = data.get("issues", [])
    overall = data.get("overall_status", "unknown")

    lines = [f"Platform health: {overall}", ""]
    for s in services:
        name = s.get("name", "?")
        status = s.get("status", "?")
        latency = s.get("latency_ms", "?")
        icon = "+" if status == "healthy" else "-" if status in ("degraded", "unreachable") else "?"
        required = " (required)" if s.get("required") else ""
        lines.append(f"  [{icon}] {name:<20s} {status:<15s} {latency}ms{required}")

    if issues:
        lines.append("")
        lines.append("Issues:")
        for issue in issues:
            lines.append(f"  ! {issue}")

    ok(
        result=data,
        next_actions=[
            {"command": "ren doctor", "description": "Full diagnostic report"},
            {"command": "ren status", "description": "Quick Trigger API health"},
        ],
        human_text="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@service_app.command("status")
def service_status(
    name: str = typer.Argument(None, help="Service name (omit for all)"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show health status for a specific service or all services.

    Without a name, shows the aggregated health summary.
    With a name, filters to that specific service.
    """
    setup(output, quiet)
    data = api_get("/control-plane/services")
    services = data.get("services", [])

    if name:
        matched = [s for s in services if s.get("name") == name]
        if not matched:
            available = ", ".join(s.get("name", "?") for s in services)
            from renaissance_cli._output import ExitCode, fail
            fail("NOT_FOUND", f"Service '{name}' not found. Available: {available}",
                 exit_code=ExitCode.NOT_FOUND)
            return
        svc = matched[0]
        lines = [
            f"Service: {svc['name']}",
            f"Kind:    {svc.get('kind', '?')}",
            f"URL:     {svc.get('url', '?')}",
            f"Status:  {svc.get('status', '?')}",
            f"Latency: {svc.get('latency_ms', '?')}ms",
        ]
        if svc.get("error"):
            lines.append(f"Error:   {svc['error']}")
        ok(result=svc, next_actions=[
            {"command": "ren service list", "description": "List all services"},
        ], human_text="\n".join(lines))
    else:
        overall = data.get("overall_status", "unknown")
        issues = data.get("issues", [])
        lines = [f"Overall: {overall}"]
        if issues:
            for issue in issues:
                lines.append(f"  ! {issue}")
        else:
            lines.append("  All required services healthy.")
        ok(result=data, next_actions=[
            {"command": "ren service list", "description": "Detailed service list"},
        ], human_text="\n".join(lines))
