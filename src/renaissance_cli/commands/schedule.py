"""ren schedule — manage Temporal cron schedules."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_delete, api_get, api_patch, api_post
from renaissance_cli._output import OutputFormat, OutputOpt, QuietOpt, YesOpt, ok, setup

schedule_app = typer.Typer(name="schedule", help="Create, list, and control cron schedules.", no_args_is_help=True)


@schedule_app.command("create")
def schedule_create(
    template: str = typer.Option(..., "--template", "-t", help="Pipeline template name"),
    target: str = typer.Option(..., "--target", help="Target identifier"),
    cron: str = typer.Option(..., "--cron", help="Cron expression (e.g. '0 */6 * * *')"),
    note: str = typer.Option(None, "--note", help="Description note"),
    schedule_id: str = typer.Option(None, "--id", help="Custom schedule ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Create a cron-triggered pipeline schedule.

    Side effects: registers a new schedule in Temporal Cloud.
    """
    setup(output, quiet)
    body: dict = {"template": template, "target": target, "cron": cron}
    if note:
        body["note"] = note
    if schedule_id:
        body["schedule_id"] = schedule_id
    data = api_post("/schedules", body)
    sid = data.get("schedule_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren schedule show {sid}", "description": "View schedule details"},
            {"command": f"ren schedule trigger {sid}", "description": "Trigger immediate run"},
            {"command": f"ren schedule delete {sid}", "description": "Remove schedule"},
        ],
        human_text=f"Schedule created: {sid}",
    )


@schedule_app.command("list")
def schedule_list(
    query: str = typer.Option(None, "--query", help="Temporal Query Language filter"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List all schedules. Supports Temporal Query Language filters."""
    setup(output, quiet)
    params: dict = {"limit": limit}
    if query:
        params["query"] = query
    data = api_get("/schedules", params=params)
    schedules = data.get("schedules", [])
    ok(
        result=data,
        next_actions=[
            {"command": f"ren schedule show {schedules[0].get('id', '?')}", "description": "View first schedule"} if schedules else
            {"command": "ren schedule create --help", "description": "Create a new schedule"},
        ],
        human_text="\n".join(
            f"  {s.get('id', '?'):40s} {'PAUSED' if s.get('paused') else 'ACTIVE':8s} {', '.join(s.get('cron_expressions', []))}"
            for s in schedules
        ) or "No schedules found.",
    )


@schedule_app.command("show")
def schedule_show(
    schedule_id: str = typer.Argument(help="Schedule ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show schedule details including next run times and recent actions."""
    setup(output, quiet)
    data = api_get(f"/schedules/{schedule_id}")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren schedule trigger {schedule_id}", "description": "Trigger immediate run"},
            {"command": f"ren schedule pause {schedule_id}", "description": "Pause schedule"},
            {"command": f"ren schedule update {schedule_id} --cron '...'", "description": "Update cron"},
        ],
        human_text=f"Schedule: {schedule_id}\n"
                   f"  Paused: {data.get('paused', '?')}\n"
                   f"  Cron: {', '.join(data.get('cron_expressions', []))}\n"
                   f"  Next: {', '.join(str(t) for t in data.get('next_action_times', [])[:3])}",
    )


@schedule_app.command("pause")
def schedule_pause(
    schedule_id: str = typer.Argument(help="Schedule ID"),
    note: str = typer.Option(None, "--note", help="Pause reason"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Pause a schedule. Side effects: stops future cron triggers."""
    setup(output, quiet)
    body: dict = {}
    if note:
        body["note"] = note
    data = api_post(f"/schedules/{schedule_id}/pause", body)
    ok(result=data, next_actions=[
        {"command": f"ren schedule resume {schedule_id}", "description": "Resume schedule"},
    ], human_text=f"Schedule {schedule_id}: paused")


@schedule_app.command("resume")
def schedule_resume(
    schedule_id: str = typer.Argument(help="Schedule ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Resume a paused schedule."""
    setup(output, quiet)
    data = api_post(f"/schedules/{schedule_id}/resume")
    ok(result=data, next_actions=[
        {"command": f"ren schedule show {schedule_id}", "description": "View schedule"},
    ], human_text=f"Schedule {schedule_id}: resumed")


@schedule_app.command("trigger")
def schedule_trigger(
    schedule_id: str = typer.Argument(help="Schedule ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Trigger an immediate one-time execution of a schedule.

    Side effects: starts a new Temporal workflow from the schedule template.
    """
    setup(output, quiet)
    data = api_post(f"/schedules/{schedule_id}/trigger")
    ok(result=data, next_actions=[
        {"command": "ren pipeline list --status Running", "description": "See triggered pipeline"},
        {"command": f"ren schedule show {schedule_id}", "description": "View schedule"},
    ], human_text=f"Schedule {schedule_id}: triggered")


@schedule_app.command("update")
def schedule_update(
    schedule_id: str = typer.Argument(help="Schedule ID"),
    cron: str = typer.Option(None, "--cron", help="New cron expression"),
    note: str = typer.Option(None, "--note", help="New description"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Update schedule cron expression or note."""
    setup(output, quiet)
    body: dict = {}
    if cron:
        body["cron"] = cron
    if note:
        body["note"] = note
    data = api_patch(f"/schedules/{schedule_id}", body)
    ok(result=data, next_actions=[
        {"command": f"ren schedule show {schedule_id}", "description": "View updated schedule"},
    ], human_text=f"Schedule {schedule_id}: updated")


@schedule_app.command("delete")
def schedule_delete(
    schedule_id: str = typer.Argument(help="Schedule ID"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Delete a schedule. Side effects: removes the schedule from Temporal.

    Requires --yes to skip confirmation in non-interactive mode.
    """
    setup(output, quiet)
    if not yes:
        typer.confirm(f"Delete schedule '{schedule_id}'?", abort=True)
    data = api_delete(f"/schedules/{schedule_id}")
    ok(result=data, next_actions=[
        {"command": "ren schedule list", "description": "View remaining schedules"},
    ], human_text=f"Schedule {schedule_id}: deleted")
