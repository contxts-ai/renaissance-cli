"""ren metrics — execution metrics and analytics."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_get
from renaissance_cli._output import OutputFormat, OutputOpt, QuietOpt, ok, setup

metrics_app = typer.Typer(name="metrics", help="View execution metrics and step analytics.", no_args_is_help=True)


@metrics_app.command("summary")
def metrics_summary(
    days: int = typer.Option(7, "--days", "-d", help="Lookback period (1-90)", min=1, max=90),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show execution summary grouped by template.

    Returns total runs, success rate, and avg duration per template.
    """
    setup(output, quiet)
    data = api_get("/metrics/summary", params={"days": days})
    templates = data.get("templates", {})
    lines = [f"Metrics (last {days} days):"]
    for name, m in templates.items():
        lines.append(f"  {name:30s} {m.get('total', 0):3d} runs, {m.get('success_rate', 0):.0%} success")
    ok(
        result=data,
        next_actions=[
            {"command": "ren metrics steps", "description": "View step-level metrics"},
            {"command": "ren pipeline list", "description": "List pipelines"},
        ],
        human_text="\n".join(lines) if templates else f"No executions in the last {days} days.",
    )


@metrics_app.command("steps")
def metrics_steps(
    days: int = typer.Option(7, "--days", "-d", help="Lookback period (1-90)", min=1, max=90),
    limit: int = typer.Option(20, "--limit", "-n", help="Max skills to show", min=1, max=100),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show step-level skill invocation metrics.

    Returns invocation counts and avg execution time per skill.
    """
    setup(output, quiet)
    data = api_get("/metrics/steps", params={"days": days, "limit": limit})
    skills = data.get("skills", {})
    lines = [f"Step metrics (last {days} days, top {limit}):"]
    for name, m in skills.items():
        avg_ms = m.get("avg_execution_time_ms", 0)
        lines.append(f"  {name:40s} {m.get('invocations', 0):4d} calls, avg {avg_ms/1000:.1f}s")
    ok(
        result=data,
        next_actions=[
            {"command": "ren metrics summary", "description": "View summary metrics"},
        ],
        human_text="\n".join(lines) if skills else "No step data found.",
    )
