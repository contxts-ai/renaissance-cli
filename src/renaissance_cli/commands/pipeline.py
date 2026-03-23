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


@pipeline_app.command("terminate")
def terminate(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Force-terminate a workflow. Use cancel for graceful shutdown."""
    setup(output, quiet)
    if not yes and sys.stdout.isatty():
        typer.confirm(f"Force-terminate {workflow_id}?", abort=True)
    data = api_post(f"/pipeline/{workflow_id}/terminate")
    ok(
        result=data,
        next_actions=[{"command": "ren pipeline list", "description": "List pipelines"}],
        human_text=f"Pipeline terminated: {workflow_id}",
    )


@pipeline_app.command("auto")
def auto_toggle(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    step_id: str = typer.Argument(help="Step ID"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Toggle auto-execution mode for a specific step."""
    setup(output, quiet)
    data = api_post(f"/pipeline/{workflow_id}/step/{step_id}/auto")
    ok(
        result=data,
        next_actions=[{"command": f"ren pipeline progress {workflow_id}", "description": "Check progress"}],
        human_text=f"Auto mode toggled: {workflow_id}/{step_id}",
    )


@pipeline_app.command("start-phase2")
def start_phase2(
    workflow_id: str = typer.Argument(help="Research workflow ID"),
    token: str = typer.Option(None, "--token", "-t", help="Single token (omit for all)"),
    output: OutputFormat = OutputOpt, quiet: bool = QuietOpt,
) -> None:
    """Start Phase 2 for a research pipeline (all tokens or a single token)."""
    setup(output, quiet)
    if token:
        data = api_post(f"/pipeline/{workflow_id}/start_phase2", {"token": token})
        msg = f"Phase 2 started for {token}"
    else:
        data = api_post(f"/pipeline/{workflow_id}/start_phase2_all")
        msg = "Phase 2 started for all tokens"
    ok(
        result=data,
        next_actions=[{"command": f"ren pipeline progress {workflow_id} --watch", "description": "Watch progress"}],
        human_text=msg,
    )


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


@pipeline_app.command("dag")
def dag(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show the DAG structure of a pipeline (steps and dependencies)."""
    setup(output, quiet)
    data = api_get(f"/pipeline/{workflow_id}/dag")
    steps = data.get("steps", [])

    lines = [f"DAG: {workflow_id}", f"Steps ({len(steps)}):"]
    na: list[dict] = []
    for s in steps:
        sid = s.get("step_id", s.get("id", "?"))
        deps = s.get("depends_on", [])
        status = s.get("status", "")
        dep_str = f" <- {', '.join(deps)}" if deps else ""
        lines.append(f"  {sid:<30s} {status}{dep_str}")
        na.append({"command": f"ren pipeline step-output {workflow_id} {sid}", "description": f"Output of {sid}"})

    ok(result=data, next_actions=na[:5], human_text="\n".join(lines))


@pipeline_app.command("step-output")
def step_output(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    step_id: str = typer.Argument(help="Step ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show the full output of a pipeline step."""
    setup(output, quiet)
    data = api_get(f"/pipeline/{workflow_id}/step/{step_id}/output")
    content = data.get("output", data.get("result", ""))

    text = f"Step: {step_id}\n"
    if isinstance(content, str):
        text += content[:3000]
        if len(content) > 3000:
            text += f"\n... ({len(content)} chars total)"
    else:
        text += json.dumps(content, indent=2, ensure_ascii=False)[:3000]

    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline step-ops {workflow_id} {step_id}", "description": "View operations"},
            {"command": f"ren pipeline dag {workflow_id}", "description": "View DAG"},
        ],
        human_text=text,
    )


@pipeline_app.command("step-ops")
def step_ops(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    step_id: str = typer.Argument(help="Step ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show artifact and KG operations performed by a step."""
    setup(output, quiet)
    data = api_get(f"/pipeline/{workflow_id}/step/{step_id}/ops")
    ops = data.get("operations", data.get("ops", []))

    lines = [f"Operations for {step_id} ({len(ops)}):"]
    for op in ops:
        op_type = op.get("type", op.get("operation", "?"))
        target = op.get("target", op.get("entity", ""))
        lines.append(f"  [{op_type}] {target}")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline step-output {workflow_id} {step_id}", "description": "View output"},
        ],
        human_text="\n".join(lines),
    )


@pipeline_app.command("function")
def function_code(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    function_id: str = typer.Argument(help="Function ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show generated function source and test code from a coding pipeline."""
    setup(output, quiet)
    data = api_get(f"/pipeline/{workflow_id}/function/{function_id}")

    source = data.get("source_file_content", "")
    test = data.get("test_file_content", "")
    status = data.get("code_status", "?")

    lines = [f"Function: {function_id} (status: {status})"]
    if source:
        lines.append("\n--- source ---")
        lines.append(source[:3000])
    if test:
        lines.append("\n--- test ---")
        lines.append(test[:3000])

    ok(result=data, next_actions=[
        {"command": f"ren pipeline progress {workflow_id}", "description": "Pipeline progress"},
    ], human_text="\n".join(lines))


@pipeline_app.command("lineage")
def lineage(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show the chain lineage of a completed pipeline."""
    setup(output, quiet)
    data = api_get(f"/pipeline/{workflow_id}/lineage")
    chain = data.get("chain", data.get("lineage", []))

    lines = [f"Lineage for {workflow_id}:"]
    for i, entry in enumerate(chain):
        wid = entry.get("workflow_id", entry) if isinstance(entry, dict) else entry
        prefix = "  -> " if i > 0 else "  "
        lines.append(f"{prefix}{wid}")

    ok(result=data, next_actions=[
        {"command": f"ren pipeline progress {workflow_id}", "description": "View progress"},
    ], human_text="\n".join(lines))


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


@pipeline_app.command("launch-backfill")
def launch_backfill(
    target: str = typer.Option(..., "--target", help="Target identifier"),
    metric_id: str = typer.Option(..., "--metric-id", help="Metric ID"),
    collector_module: str = typer.Option(..., "--collector-module", help="Collector module path"),
    collector_function: str = typer.Option(..., "--collector-function", help="Collector function name"),
    start_block: int = typer.Option(..., "--start-block", help="Start block number"),
    end_block: int = typer.Option(..., "--end-block", help="End block number"),
    strategy: str = typer.Option(None, "--strategy", help="Backfill strategy"),
    sampling_grain: str = typer.Option(None, "--sampling-grain", help="Sampling grain"),
    partition_size: int = typer.Option(None, "--partition-size", help="Partition size in blocks"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Dry run without writing data"),
    truth_set: str = typer.Option(None, "--truth-set", help="Path to truth set file"),
    output_dir: str = typer.Option(None, "--output-dir", help="Output directory"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a historical data backfill pipeline.

    Side effects: creates a backfill workflow in Temporal.
    """
    setup(output, quiet)
    body: dict = {
        "target": target,
        "metric_id": metric_id,
        "collector_module": collector_module,
        "collector_function": collector_function,
        "start_block": start_block,
        "end_block": end_block,
    }
    if strategy:
        body["backfill_strategy"] = strategy
    if sampling_grain:
        body["sampling_grain"] = sampling_grain
    if partition_size is not None:
        body["partition_size_blocks"] = partition_size
    if dry_run:
        body["dry_run"] = True
    if truth_set:
        body["truth_set_path"] = truth_set
    if output_dir:
        body["output_dir"] = output_dir

    data = api_post("/pipeline/backfill", body)
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline backfill-progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Backfill launched: {wf_id}",
    )


@pipeline_app.command("backfill-progress")
def backfill_progress(
    workflow_id: str = typer.Argument(help="Backfill workflow ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll until terminal state"),
    interval: int = typer.Option(3, "--interval", help="Poll interval in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show backfill pipeline progress."""
    setup(output, quiet)
    _watch_progress(
        f"/pipeline/backfill/{workflow_id}/progress",
        workflow_id, "Backfill", watch, interval, output,
    )


@pipeline_app.command("launch-backfill-build")
def launch_backfill_build(
    target: str = typer.Option(..., "--target", "-t", help="Target identifier"),
    steps_file: str = typer.Option(..., "--steps-file", "-s", help="Path to steps JSON file"),
    max_iter_per_step: int = typer.Option(None, "--max-iter-per-step", help="Max iterations per step"),
    convergence_threshold: float = typer.Option(None, "--convergence-threshold", help="Convergence score threshold"),
    coding_model: str = typer.Option(None, "--coding-model", help="Model for code generation"),
    verifier_model: str = typer.Option(None, "--verifier-model", help="Model for verification"),
    critique_model: str = typer.Option(None, "--critique-model", help="Model for critique"),
    pause_between_steps: bool = typer.Option(True, "--pause/--no-pause", help="Pause between steps"),
    reference_dir: str = typer.Option(None, "--reference-dir", help="Reference directory path"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch a backfill-build pipeline (orchestrated Ralph Loops with artifact deps).

    Requires a --steps-file with the step definitions JSON.
    Side effects: creates a BackfillBuild workflow in Temporal.
    """
    setup(output, quiet)

    try:
        with open(steps_file) as f:
            steps = json.load(f)
    except Exception as e:
        from renaissance_cli._output import ExitCode, fail
        fail("BAD_REQUEST", f"Cannot read steps file: {e}", exit_code=ExitCode.USAGE_ERROR)
        return

    body: dict = {
        "target": target,
        "steps": steps,
        "pause_between_steps": pause_between_steps,
    }
    if max_iter_per_step is not None:
        body["max_iterations_per_step"] = max_iter_per_step
    if convergence_threshold is not None:
        body["convergence_threshold"] = convergence_threshold
    if coding_model:
        body["coding_model"] = coding_model
    if verifier_model:
        body["verifier_model"] = verifier_model
    if critique_model:
        body["critique_model"] = critique_model
    if reference_dir:
        body["reference_dir"] = reference_dir

    data = api_post("/pipeline/backfill-build", body)
    wf_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline backfill-build-progress {wf_id}", "description": "Watch progress"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Backfill-build launched: {wf_id}",
    )


@pipeline_app.command("backfill-build-progress")
def backfill_build_progress(
    workflow_id: str = typer.Argument(help="Backfill-build workflow ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll until terminal state"),
    interval: int = typer.Option(3, "--interval", help="Poll interval in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show backfill-build pipeline progress."""
    setup(output, quiet)
    _watch_progress(
        f"/pipeline/backfill-build/{workflow_id}/progress",
        workflow_id, "Backfill-build", watch, interval, output,
    )


def _watch_progress(
    path: str, workflow_id: str, label: str,
    watch: bool, interval: int, output: OutputFormat | None,
) -> None:
    """Generic watch loop for progress endpoints."""
    data = api_get(path)
    status = data.get("status", "unknown")

    if not watch:
        ok(
            result=data,
            next_actions=[
                {"command": f"ren pipeline progress {workflow_id} --watch", "description": "Watch live"},
                {"command": f"ren pipeline cancel {workflow_id}", "description": "Cancel"},
            ],
            human_text=_format_progress(workflow_id, data),
        )
        return

    while True:
        data = api_get(path)
        status = data.get("status", "unknown")

        if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
            typer.clear()
            typer.echo(_format_progress(workflow_id, data))
        else:
            emit(data)

        if status in TERMINAL_STATES:
            break
        time.sleep(interval)

    if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
        typer.echo(f"\n{label} {status}.")
    else:
        ok(result=data, next_actions=[
            {"command": "ren pipeline list", "description": "List pipelines"},
        ])


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


@pipeline_app.command("batch")
def batch_launch(
    template: str = typer.Option(..., "--template", "-t", help="Template name"),
    targets: str = typer.Option(..., "--targets", help="Comma-separated target list"),
    pause: bool = typer.Option(True, "--pause/--no-pause", help="Pause between steps"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Launch the same pipeline template for multiple targets.

    Side effects: creates one workflow per target.
    """
    setup(output, quiet)
    target_list = [t.strip() for t in targets.split(",") if t.strip()]
    data = api_post("/pipelines/batch", {
        "template": template,
        "targets": target_list,
        "pause_between_steps": pause,
    })
    workflows = data.get("workflows", [])
    lines = [f"Batch launched ({len(workflows)} workflows):"]
    for w in workflows:
        lines.append(f"  {w.get('workflow_id', w.get('target', '?'))}")

    ok(
        result=data,
        next_actions=[
            {"command": "ren pipeline list --status Running", "description": "List running pipelines"},
        ],
        human_text="\n".join(lines),
    )


@pipeline_app.command("batch-resume")
def batch_resume(
    workflow_ids: str = typer.Argument(help="Comma-separated workflow IDs"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Resume multiple paused pipelines at once."""
    setup(output, quiet)
    ids = [w.strip() for w in workflow_ids.split(",") if w.strip()]
    data = api_post("/pipelines/batch/resume", {"workflow_ids": ids})
    ok(
        result=data,
        next_actions=[{"command": "ren pipeline list --status Running", "description": "List running"}],
        human_text=f"Batch resumed: {len(ids)} workflows",
    )


@pipeline_app.command("batch-cancel")
def batch_cancel(
    workflow_ids: str = typer.Argument(help="Comma-separated workflow IDs"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Cancel multiple pipelines at once."""
    setup(output, quiet)
    ids = [w.strip() for w in workflow_ids.split(",") if w.strip()]
    if not yes and sys.stdout.isatty():
        typer.confirm(f"Cancel {len(ids)} workflows?", abort=True)
    data = api_post("/pipelines/batch/cancel", {"workflow_ids": ids})
    ok(
        result=data,
        next_actions=[{"command": "ren pipeline list", "description": "List pipelines"}],
        human_text=f"Batch cancelled: {len(ids)} workflows",
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@pipeline_app.command("replay")
def replay(
    workflow_id: str = typer.Argument(help="Completed workflow ID to replay"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Replay a completed pipeline with the same configuration.

    Side effects: creates a new workflow execution.
    """
    setup(output, quiet)
    if not yes and sys.stdout.isatty():
        typer.confirm(f"Replay {workflow_id}?", abort=True)
    data = api_post(f"/pipeline/{workflow_id}/replay")
    new_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {new_id} --watch", "description": "Watch new pipeline"},
        ],
        human_text=f"Replayed: {workflow_id} -> {new_id}",
    )


@pipeline_app.command("replay-from")
def replay_from(
    workflow_id: str = typer.Argument(help="Completed workflow ID"),
    step_id: str = typer.Argument(help="Step ID to replay from"),
    yes: bool = YesOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Replay a pipeline from a specific step onwards.

    Side effects: creates a new workflow execution.
    """
    setup(output, quiet)
    if not yes and sys.stdout.isatty():
        typer.confirm(f"Replay {workflow_id} from step {step_id}?", abort=True)
    data = api_post(f"/pipeline/{workflow_id}/replay/from/{step_id}")
    new_id = data.get("workflow_id", "unknown")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline progress {new_id} --watch", "description": "Watch new pipeline"},
        ],
        human_text=f"Replayed from {step_id}: {workflow_id} -> {new_id}",
    )
