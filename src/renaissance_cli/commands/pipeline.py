"""ren pipeline — launch, monitor, and control Temporal pipelines."""

from __future__ import annotations

import json
import re
import sys
import time

import typer

from renaissance_cli._client import api_get, api_post
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    YesOpt,
    emit,
    logger,
    ok,
    setup,
)

pipeline_app = typer.Typer(name="pipeline", help="Launch, monitor, and control pipelines.", no_args_is_help=True)

TERMINAL_STATES = {"completed", "failed", "cancelled", "partial_failure", "completed_degraded"}


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


@pipeline_app.command("launch")
def launch(
    template: str = typer.Option(..., "--template", "-t", help="Template name"),
    target: str = typer.Option(..., "--target", help="Target identifier (e.g. wstETH)"),
    pause: bool = typer.Option(True, "--pause/--no-pause", help="Pause between steps"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a pipeline from a template.

    Starts a Temporal workflow and returns the workflow_id for tracking.
    Side effects: creates a new Temporal workflow execution.
    """
    setup(output, quiet)
    logger.info("Launching pipeline: template=%s target=%s", template, target)
    data = api_post("/pipeline/from-template", {
        "template": template,
        "target": target,
        "pause_between_steps": pause,
    })
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline progress {wf_id} --watch", "description": "Watch live"},
            {"command": f"ren pipeline pause {wf_id}", "description": "Pause pipeline"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel pipeline"},
        ],
        human_text=f"Pipeline launched: {wf_id}",
    )


@pipeline_app.command("launch-research")
def launch_research(
    target: str = typer.Option(..., "--target", help="Research target"),
    pause: bool = typer.Option(True, "--pause/--no-pause", help="Pause between steps"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a research pipeline (2-phase token research fan-out).

    Side effects: creates a new research workflow in Temporal.
    """
    setup(output, quiet)
    data = api_post("/pipeline/research", {"target": target, "pause_between_steps": pause})
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Research pipeline launched: {wf_id}",
    )


@pipeline_app.command("launch-coding")
def launch_coding(
    target: str = typer.Option(..., "--target", help="Coding target"),
    pause: bool = typer.Option(True, "--pause/--no-pause", help="Pause between steps"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a coding pipeline (code generation + review + PR).

    Side effects: creates a coding workflow, may generate PRs.
    """
    setup(output, quiet)
    data = api_post("/pipeline/coding", {"target": target, "pause_between_steps": pause})
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Coding pipeline launched: {wf_id}",
    )


@pipeline_app.command("launch-forge")
def launch_forge(
    skill: str = typer.Option(..., "--skill", help="Skill name to improve"),
    pause: bool = typer.Option(True, "--pause/--no-pause", help="Pause between steps"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch skill-forge (iterative skill test + eval + improve loop).

    Side effects: modifies skill files, runs evals.
    """
    setup(output, quiet)
    data = api_post("/pipeline/skill-forge", {"target": skill, "pause_between_steps": pause})
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Skill-forge launched: {wf_id}",
    )


@pipeline_app.command("orchestrate")
def orchestrate(
    goal: str = typer.Option(..., "--goal", help="Free-form goal description"),
    target: str = typer.Option(..., "--target", help="Target identifier"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a goal-driven orchestration pipeline.

    The orchestrator selects and composes skills to achieve the goal.
    Side effects: creates a custom workflow based on the goal.
    """
    setup(output, quiet)
    data = api_post("/pipeline/orchestrate", {"goal": goal, "target": target})
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Orchestration launched: {wf_id}",
    )


# ---------------------------------------------------------------------------
# Ralph Loop
# ---------------------------------------------------------------------------


@pipeline_app.command("ralph-spec")
def ralph_spec(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show FunctionSpec schema, required fields, and examples for Ralph Loop.

    Returns JSON schema with examples. Use to construct a valid --spec file.
    Requires: Trigger API running.
    """
    setup(output, quiet)
    data = api_get("/pipeline/ralph-loop/spec-schema")

    lines = ["Required: " + ", ".join(data.get("required_minimal", []))]
    lines.append(f"Kinds: {', '.join(data.get('component_kinds', []))}")
    for ex in data.get("examples", []):
        lines.append(f"\nExample ({ex['label']}):")
        lines.append(json.dumps(ex["spec"], indent=2))
    ok(result=data, next_actions=data.get("next_actions", []), human_text="\n".join(lines))


def _slugify(text: str) -> str:
    """Convert text to a valid function name / ID slug."""
    s = re.sub(r"[^a-zA-Z0-9_\s-]", "", text.lower().strip())
    s = re.sub(r"[\s-]+", "_", s)
    return s[:60] or "unnamed"


@pipeline_app.command("launch-ralph")
def launch_ralph(
    target: str = typer.Option(..., "--target", "-t", help="Target identifier"),
    spec_file: str = typer.Option(None, "--spec", "-s", help="Path to function_spec JSON file"),
    describe: str = typer.Option(None, "--describe", "-d", help="Natural language description (auto-generates minimal spec)"),
    name: str = typer.Option(None, "--name", "-n", help="Function name (with --describe)"),
    kind: str = typer.Option("generic", "--kind", "-k", help="Component kind (generic, ingestion, signal, ...)"),
    max_iter: int = typer.Option(8, "--max-iter", help="Max convergence iterations (1-20)"),
    threshold: float = typer.Option(0.85, "--threshold", help="Convergence score threshold (0.0-1.0)"),
    no_pause: bool = typer.Option(False, "--no-pause", help="Skip plan review HITL gate"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a Ralph Loop convergence pipeline (code -> verify -> critique -> converge).

    Three modes:
    1. --spec path/to/spec.json: Full FunctionSpec file
    2. --describe "..." --name fn: Auto-generate minimal spec from description
    3. Neither: Run coding-planner first (requires target with upstream data)

    Returns workflow_id. Use --output json for structured result.
    Side effects: starts a Temporal workflow, generates code, may create PRs.

    Examples:
        ren pipeline launch-ralph -t test --describe "Add two numbers" --name add_numbers
        ren pipeline launch-ralph -t myproject --spec ./my_spec.json
        ren pipeline launch-ralph -t wstETH
    """
    setup(output, quiet)

    body: dict = {
        "target": target,
        "max_iterations": max_iter,
        "convergence_threshold": threshold,
        "pause_after_plan": not no_pause,
    }

    if spec_file:
        # Mode 1: spec file
        try:
            with open(spec_file) as f:
                spec = json.load(f)
        except Exception as e:
            from renaissance_cli._output import ExitCode, fail
            fail("BAD_REQUEST", f"Cannot read spec file: {e}", exit_code=ExitCode.USAGE_ERROR)
            return
        body["function_spec"] = spec
        logger.info("Using spec from %s", spec_file)

    elif describe:
        # Mode 2: auto-generate minimal spec
        fn_name = _slugify(name or describe[:40])
        spec = {
            "function_id": fn_name,
            "function_name": fn_name,
            "description": describe,
            "component_kind": kind,
            "promotion_mode": "workspace_only",
        }

        if not yes and sys.stdout.isatty():
            typer.echo("Generated spec:")
            typer.echo(json.dumps(spec, indent=2))
            typer.confirm("Launch with this spec?", abort=True)

        body["function_spec"] = spec
        logger.info("Generated minimal spec: %s", fn_name)

    else:
        # Mode 3: coding-planner (needs upstream data)
        logger.info("No --spec or --describe — will run coding-planner for %s", target)

    data = api_post("/pipeline/ralph-loop", body)
    wf_id = data.get("workflow_id", "unknown")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline progress {wf_id} --watch", "description": "Live monitor"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Ralph Loop launched: {wf_id}",
    )


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


@pipeline_app.command("progress")
def progress(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll until terminal state"),
    interval: int = typer.Option(3, "--interval", help="Poll interval in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show pipeline progress. Use --watch to poll until completion.

    Returns step-by-step status, completed/failed counts, and pause state.
    """
    setup(output, quiet)
    data = api_get(f"/pipeline/{workflow_id}/progress")

    if not watch:
        status = data.get("status", "unknown")
        na = _progress_next_actions(workflow_id, status, data)
        ok(result=data, next_actions=na, human_text=_format_progress(workflow_id, data))
        return

    # Watch mode
    while True:
        data = api_get(f"/pipeline/{workflow_id}/progress")
        status = data.get("status", "unknown")

        if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
            typer.clear()
            typer.echo(_format_progress(workflow_id, data))
        else:
            emit(data)

        if status in TERMINAL_STATES:
            break
        time.sleep(interval)

    na = _progress_next_actions(workflow_id, status, data)
    if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
        typer.echo(f"\nPipeline {status}.")
    else:
        ok(result=data, next_actions=na)


def _progress_next_actions(wf_id: str, status: str, data: dict) -> list[dict]:
    if status in TERMINAL_STATES:
        return [
            {"command": "ren pipeline list", "description": "List pipelines"},
            {"command": "ren metrics summary", "description": "View metrics"},
        ]
    actions = []
    if data.get("paused"):
        actions.append({"command": f"ren pipeline resume {wf_id}", "description": "Resume"})
        actions.append({"command": f"ren pipeline approve {wf_id}", "description": "Approve"})
    else:
        actions.append({"command": f"ren pipeline pause {wf_id}", "description": "Pause"})
    actions.append({"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"})
    return actions


def _format_progress(wf_id: str, data: dict) -> str:
    status = data.get("status", "unknown")
    completed = data.get("completed_steps", [])
    running = data.get("running_steps", [])
    failed = data.get("failed_steps", [])
    paused = data.get("paused", False)
    lines = [
        f"Pipeline: {wf_id}",
        f"Status:   {status}" + (" (PAUSED)" if paused else ""),
        f"Steps:    {len(completed)} completed, {len(running)} running, {len(failed)} failed",
    ]
    if data.get("pause_context"):
        lines.append(f"Paused at: {data['pause_context']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pipeline_app.command("list")
def list_pipelines(
    status_filter: str = typer.Option("Running", "--status", "-s", help="Running|Completed|All"),
    prefix: str = typer.Option(None, "--prefix", help="Filter by workflow ID prefix"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List pipelines by status.

    Returns workflow IDs, statuses, and start times.
    """
    setup(output, quiet)
    params: dict = {"limit": limit}
    if prefix:
        params["prefix"] = prefix

    if status_filter.lower() in ("running", "all"):
        running = api_get("/pipelines/status", params={**params, "status": "Running"})
    else:
        running = {"workflows": []}

    if status_filter.lower() in ("completed", "all"):
        completed = api_get("/pipelines/completed", params=params)
    else:
        completed = {"workflows": []}

    all_wfs = running.get("workflows", []) + completed.get("workflows", [])
    ok(
        result={"count": len(all_wfs), "workflows": all_wfs},
        next_actions=[
            {"command": f"ren pipeline progress {all_wfs[0].get('workflow_id', '?')}", "description": "View first pipeline"} if all_wfs else
            {"command": "ren template list", "description": "Browse templates to launch"},
        ],
        human_text="\n".join(
            f"  {w.get('workflow_id', '?'):50s} {w.get('status', '?')}"
            for w in all_wfs
        ) or "No pipelines found.",
    )


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------


def _control(workflow_id: str, action: str, step_id: str | None = None,
             output: OutputFormat | None = None, quiet: bool = False) -> None:
    setup(output, quiet)
    if step_id:
        path = f"/pipeline/{workflow_id}/skip/{step_id}"
    else:
        path = f"/pipeline/{workflow_id}/{action}"
    data = api_post(path)
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {workflow_id}", "description": "Check progress"},
        ],
        human_text=f"Pipeline {workflow_id}: {action}",
    )


@pipeline_app.command("pause")
def pause(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Pause a running pipeline. Side effects: sends pause signal to Temporal."""
    _control(workflow_id, "pause", output=output, quiet=quiet)


@pipeline_app.command("resume")
def resume(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Resume a paused pipeline."""
    _control(workflow_id, "resume", output=output, quiet=quiet)


@pipeline_app.command("approve")
def approve(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Approve a pipeline waiting at a HITL gate."""
    _control(workflow_id, "approve", output=output, quiet=quiet)


@pipeline_app.command("cancel")
def cancel(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Cancel a running pipeline. Side effects: terminates the Temporal workflow."""
    _control(workflow_id, "cancel", output=output, quiet=quiet)


@pipeline_app.command("skip")
def skip(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    step_id: str = typer.Argument(help="Step ID to skip"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Skip a specific step in a paused pipeline."""
    _control(workflow_id, "skip", step_id=step_id, output=output, quiet=quiet)
