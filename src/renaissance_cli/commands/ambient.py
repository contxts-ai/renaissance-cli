"""ren ambient — manage and monitor ambient decision agents."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_delete, api_get, api_post
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    YesOpt,
    logger,
    ok,
    setup,
)

ambient_app = typer.Typer(
    name="ambient",
    help="Manage and monitor ambient decision agents.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@ambient_app.command("list")
def ambient_list(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List active ambient schedules.

    Returns mission IDs and their schedule status.
    """
    setup(output, quiet)
    data = api_get("/ambient/schedules")
    schedules = data.get("schedules", data if isinstance(data, list) else [])

    lines = [f"Ambient schedules ({len(schedules)}):"]
    for s in schedules:
        mid = s.get("mission_id", s.get("schedule_id", "?"))
        lines.append(f"  {mid}")

    ok(
        result={"schedules": schedules, "count": len(schedules)},
        next_actions=[
            {"command": "ren ambient status <MISSION_ID>", "description": "Check decision history"},
            {"command": "ren ambient wake <MISSION_ID>", "description": "Trigger a decision"},
        ],
        human_text="\n".join(lines) if schedules else "No active ambient schedules.",
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@ambient_app.command("status")
def ambient_status(
    mission_id: str = typer.Argument(help="Mission ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show recent decision executions for a mission.

    Returns decision history with reasoning and actions taken.
    """
    setup(output, quiet)
    data = api_get(f"/ambient/status/{mission_id}")
    executions = data.get("executions", data.get("decisions", []))

    lines = [f"Mission: {mission_id}", f"Recent executions: {len(executions)}"]
    for ex in executions[:5]:
        ts = ex.get("timestamp", ex.get("created_at", "?"))
        action = ex.get("action", ex.get("decision", "?"))
        lines.append(f"  [{ts}] {action}")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren ambient wake {mission_id}", "description": "Trigger decision now"},
            {"command": "ren ambient list", "description": "List all schedules"},
        ],
        human_text="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# Wake
# ---------------------------------------------------------------------------


@ambient_app.command("wake")
def wake(
    mission_id: str = typer.Argument(help="Mission ID to wake"),
    reason: str = typer.Option(None, "--reason", "-r", help="Wake reason"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Manually trigger an ambient decision workflow.

    Side effects: starts a decision workflow in Temporal.
    """
    setup(output, quiet)
    body: dict = {"mission_id": mission_id}
    if reason:
        body["wake_reason"] = reason

    logger.info("Waking ambient agent: mission=%s", mission_id)
    data = api_post("/ambient/wake", body)
    wf_id = data.get("workflow_id", "unknown")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren ambient status {mission_id}", "description": "Check decision history"},
            {"command": f"ren eval result {wf_id}", "description": "Check workflow result"},
        ],
        human_text=f"Ambient wake triggered: {wf_id}",
    )


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


@ambient_app.command("schedule")
def schedule_create(
    mission_id: str = typer.Argument(help="Mission ID to schedule"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Create a 5-minute recurring schedule for a mission.

    Side effects: creates a Temporal native schedule.
    """
    setup(output, quiet)
    logger.info("Creating ambient schedule: mission=%s", mission_id)
    data = api_post(f"/ambient/schedule/{mission_id}")

    ok(
        result=data,
        next_actions=[
            {"command": "ren ambient list", "description": "List all schedules"},
            {"command": f"ren ambient status {mission_id}", "description": "Check decision history"},
        ],
        human_text=f"Ambient schedule created for: {mission_id}",
    )


# ---------------------------------------------------------------------------
# Unschedule
# ---------------------------------------------------------------------------


@ambient_app.command("unschedule")
def unschedule(
    mission_id: str = typer.Argument(help="Mission ID to unschedule"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Delete the recurring schedule for a mission.

    Side effects: removes the Temporal schedule.
    """
    setup(output, quiet)

    if not yes and typer.confirm(f"Delete ambient schedule for '{mission_id}'?", abort=True):
        pass

    logger.info("Deleting ambient schedule: mission=%s", mission_id)
    data = api_delete(f"/ambient/schedule/{mission_id}")

    ok(
        result=data,
        next_actions=[
            {"command": "ren ambient list", "description": "List remaining schedules"},
        ],
        human_text=f"Ambient schedule deleted: {mission_id}",
    )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@ambient_app.command("policy")
def policy(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show default AutonomyPolicy values.

    Returns the default policy configuration for ambient agents.
    """
    setup(output, quiet)
    data = api_get("/ambient/policy/defaults")

    lines = ["Default Autonomy Policy:"]
    for key, val in data.items():
        lines.append(f"  {key}: {val}")

    ok(
        result=data,
        next_actions=[
            {"command": "ren ambient list", "description": "List active schedules"},
        ],
        human_text="\n".join(lines),
    )
