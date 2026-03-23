"""ren agent — list, run, and monitor registered agents."""

from __future__ import annotations

import json
import sys
import time

import typer

from renaissance_cli._client import api_get, api_post
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    emit,
    logger,
    ok,
    setup,
)

agent_app = typer.Typer(
    name="agent",
    help="List, run, and monitor registered agents.",
    no_args_is_help=True,
)

TERMINAL_STATES = {"completed", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@agent_app.command("list")
def agent_list(
    standalone: bool = typer.Option(False, "--standalone", help="Show only standalone agents"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List all registered agents with their capabilities.

    Returns agent name, description, standalone flag, and deps schema.
    Requires: Trigger API running with agents loaded.
    """
    setup(output, quiet)
    data = api_get("/agents")
    agents = data.get("agents", [])

    if standalone:
        agents = [a for a in agents if a.get("standalone")]

    lines: list[str] = []
    for a in agents:
        flag = "✓" if a.get("standalone") else " "
        lines.append(f"  [{flag}] {a['name']:<28s} {a.get('description', '')[:60]}")

    human = f"Agents ({len(agents)}):\n" + "\n".join(lines) if lines else "No agents found."
    ok(
        result={"agents": agents, "count": len(agents)},
        next_actions=[
            {"command": "ren agent run <name> --target <T>", "description": "Run an agent"},
            {"command": "ren agent list --standalone", "description": "Show standalone agents only"},
        ],
        human_text=human,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@agent_app.command("run")
def agent_run(
    agent_name: str = typer.Argument(help="Agent name (e.g. artifact-agent, freshness-monitor)"),
    target: str = typer.Option("", "--target", "-t", help="Target identifier (e.g. wstETH)"),
    param: list[str] = typer.Option([], "--param", "-p", help="Extra param as key=value (repeatable)"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll progress until completion"),
    interval: int = typer.Option(5, "--interval", help="Polling interval in seconds (with --watch)"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Run a registered agent as a standalone workflow.

    Returns workflow_id. Use --watch to poll until completion.
    Side effects: starts a Temporal workflow.

    Examples:
        ren agent run artifact-agent -t wstETH -p 'workspace_dirs=["/path/ws"]'
        ren agent run freshness-monitor -p max_age_days=7
        ren agent run orchestrator -t wstETH -p 'goal=Analyze wstETH risk'
    """
    setup(output, quiet)

    body: dict = {"agent_name": agent_name}
    if target:
        body["target"] = target

    # Parse --param key=value pairs
    for p in param:
        if "=" not in p:
            logger.warning("Skipping malformed param (no '='): %s", p)
            continue
        key, raw_value = p.split("=", 1)
        # Try parsing as JSON for lists/dicts/numbers
        try:
            body[key] = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            body[key] = raw_value

    data = api_post("/pipeline/agent", body)
    wf_id = data.get("workflow_id", "unknown")

    na = [
        {"command": f"ren agent status {wf_id}", "description": "Check progress"},
        {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
    ]

    if not watch:
        ok(result=data, next_actions=na, human_text=f"Agent started: {wf_id}")
        return

    # Watch mode — poll until terminal
    logger.info("Watching %s (every %ds)...", wf_id, interval)
    while True:
        result_data = api_get(f"/result/{wf_id}")
        status = result_data.get("status", "unknown")

        if sys.stdout.isatty():
            typer.echo(f"\r  [{agent_name}] {status}", nl=False)
        else:
            emit(result_data)

        if status in TERMINAL_STATES:
            if sys.stdout.isatty():
                typer.echo()  # newline after \r
            ok(result=result_data, next_actions=na, human_text=f"Agent finished: {status}")
            return

        time.sleep(interval)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@agent_app.command("status")
def agent_status(
    workflow_id: str = typer.Argument(help="Agent workflow ID (agent-<name>-<target>-<hash>)"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Check progress of a running agent workflow.

    Returns current status and output (if completed).
    """
    setup(output, quiet)
    data = api_get(f"/result/{workflow_id}")
    status = data.get("status", "unknown")

    na = []
    if status not in TERMINAL_STATES:
        na.append({"command": f"ren agent status {workflow_id}", "description": "Check again"})
        na.append({"command": f"ren pipeline cancel {workflow_id}", "description": "Cancel"})

    ok(result=data, next_actions=na, human_text=f"[{workflow_id}] {status}")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@agent_app.command("schema")
def agent_schema(
    agent_name: str = typer.Argument(help="Agent name"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show input schema for an agent (auto-injected fields excluded).

    Returns the projected JSON Schema for user-settable fields only.
    """
    setup(output, quiet)
    data = api_get(f"/capabilities/{agent_name}/schema")

    schema = data.get("input_schema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    lines = [f"Agent: {agent_name}", "", "Input fields:"]
    for field_name, field_def in props.items():
        ftype = field_def.get("type", "any")
        req = " (required)" if field_name in required else ""
        lines.append(f"  {field_name}: {ftype}{req}")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren agent run {agent_name} --target ...", "description": "Run this agent"},
            {"command": "ren capability list --kind agent", "description": "List all agents"},
        ],
        human_text="\n".join(lines),
    )
