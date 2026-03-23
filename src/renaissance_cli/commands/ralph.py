"""ren ralph — launch, monitor, and inspect Ralph Loop convergence pipelines."""

from __future__ import annotations

import json
import re
import sys
import time

import typer

from renaissance_cli._client import api_get, api_post
from renaissance_cli._output import (
    ExitCode,
    OutputFormat,
    OutputOpt,
    QuietOpt,
    YesOpt,
    emit,
    fail,
    logger,
    ok,
    setup,
)

ralph_app = typer.Typer(
    name="ralph",
    help="Launch, monitor, and inspect Ralph Loop convergence pipelines.",
    no_args_is_help=True,
)

TERMINAL_STATES = {"completed", "failed", "cancelled", "partial_failure", "completed_degraded"}


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert text to a valid function name / ID slug."""
    s = re.sub(r"[^a-zA-Z0-9_\s-]", "", text.lower().strip())
    s = re.sub(r"[\s-]+", "_", s)
    return s[:60] or "unnamed"


@ralph_app.command("launch")
def launch(
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
        ren ralph launch -t test --describe "Add two numbers" --name add_numbers
        ren ralph launch -t myproject --spec ./my_spec.json
        ren ralph launch -t wstETH
    """
    setup(output, quiet)

    body: dict = {
        "target": target,
        "max_iterations": max_iter,
        "convergence_threshold": threshold,
        "pause_after_plan": not no_pause,
    }

    if spec_file:
        try:
            with open(spec_file) as f:
                spec = json.load(f)
        except Exception as e:
            fail("BAD_REQUEST", f"Cannot read spec file: {e}", exit_code=ExitCode.USAGE_ERROR)
            return
        body["function_spec"] = spec
        logger.info("Using spec from %s", spec_file)

    elif describe:
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
        logger.info("No --spec or --describe — will run coding-planner for %s", target)

    data = api_post("/pipeline/ralph-loop", body)
    wf_id = data.get("workflow_id", "unknown")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren ralph progress {wf_id}", "description": "Check progress"},
            {"command": f"ren ralph progress {wf_id} --watch", "description": "Watch live"},
            {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
        ],
        human_text=f"Ralph Loop launched: {wf_id}",
    )


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


@ralph_app.command("spec")
def spec(
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


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


@ralph_app.command("progress")
def progress(
    workflow_id: str = typer.Argument(help="Ralph Loop workflow ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll until terminal state"),
    interval: int = typer.Option(3, "--interval", help="Poll interval in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show Ralph Loop progress with iteration-level detail.

    Returns convergence score, iteration count, and per-function status.
    Use --watch to poll until completion.
    """
    setup(output, quiet)

    if not watch:
        data = api_get(f"/pipeline/ralph-loop/{workflow_id}/progress")
        status = data.get("status", "unknown")
        ok(
            result=data,
            next_actions=_progress_next_actions(workflow_id, status, data),
            human_text=_format_ralph_progress(workflow_id, data),
        )
        return

    while True:
        data = api_get(f"/pipeline/ralph-loop/{workflow_id}/progress")
        status = data.get("status", "unknown")

        if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
            typer.clear()
            typer.echo(_format_ralph_progress(workflow_id, data))
        else:
            emit(data)

        if status in TERMINAL_STATES:
            break
        time.sleep(interval)

    na = _progress_next_actions(workflow_id, status, data)
    if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
        typer.echo(f"\nRalph Loop {status}.")
    else:
        ok(result=data, next_actions=na)


def _progress_next_actions(wf_id: str, status: str, data: dict) -> list[dict]:
    if status in TERMINAL_STATES:
        return [
            {"command": f"ren ralph workspace {wf_id} --function <FID>", "description": "Browse workspace"},
            {"command": "ren pipeline list", "description": "List pipelines"},
        ]
    actions: list[dict] = [
        {"command": f"ren ralph progress {wf_id} --watch", "description": "Watch live"},
        {"command": f"ren pipeline pause {wf_id}", "description": "Pause"},
        {"command": f"ren pipeline cancel {wf_id}", "description": "Cancel"},
    ]
    return actions


def _format_ralph_progress(wf_id: str, data: dict) -> str:
    status = data.get("status", "unknown")
    iteration = data.get("current_iteration", "?")
    max_iter = data.get("max_iterations", "?")
    score = data.get("convergence_score")
    threshold = data.get("convergence_threshold")
    functions = data.get("functions", [])

    score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
    threshold_str = f"{threshold:.2f}" if isinstance(threshold, (int, float)) else "—"

    lines = [
        f"Ralph Loop: {wf_id}",
        f"Status:     {status}",
        f"Iteration:  {iteration}/{max_iter} (score: {score_str}, threshold: {threshold_str})",
    ]

    if functions:
        converged = sum(1 for f in functions if f.get("converged"))
        lines.append(f"Functions:  {converged} converged, {len(functions) - converged} in-progress")
        for fn in functions:
            mark = "+" if fn.get("converged") else " "
            fn_score = fn.get("score")
            fn_score_str = f"{fn_score:.2f}" if isinstance(fn_score, (int, float)) else "—"
            lines.append(f"  [{mark}] {fn.get('function_id', '?'):<30s} score={fn_score_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Function progress
# ---------------------------------------------------------------------------


@ralph_app.command("function")
def function_progress(
    workflow_id: str = typer.Argument(help="Ralph Loop workflow ID"),
    function_id: str = typer.Argument(help="Function ID"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll until converged or terminal"),
    interval: int = typer.Option(5, "--interval", help="Poll interval in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show per-function iteration history and convergence status.

    Returns iteration scores, verifier results, and convergence state.
    """
    setup(output, quiet)

    if not watch:
        data = api_get(f"/pipeline/ralph-loop/{workflow_id}/function/{function_id}/progress")
        ok(
            result=data,
            next_actions=[
                {"command": f"ren ralph workspace {workflow_id} --function {function_id}", "description": "Browse workspace files"},
                {"command": f"ren ralph progress {workflow_id}", "description": "Overall progress"},
            ],
            human_text=_format_function_progress(function_id, data),
        )
        return

    while True:
        data = api_get(f"/pipeline/ralph-loop/{workflow_id}/function/{function_id}/progress")
        converged = data.get("converged", False)
        wf_status = data.get("workflow_status", "")

        if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
            typer.clear()
            typer.echo(_format_function_progress(function_id, data))
        else:
            emit(data)

        if converged or wf_status in TERMINAL_STATES:
            break
        time.sleep(interval)

    if sys.stdout.isatty() and (output is None or output == OutputFormat.text):
        typer.echo(f"\nFunction {'converged' if converged else wf_status}.")
    else:
        ok(result=data, next_actions=[
            {"command": f"ren ralph workspace {workflow_id} --function {function_id}", "description": "Browse workspace"},
        ])


def _format_function_progress(function_id: str, data: dict) -> str:
    converged = data.get("converged", False)
    iterations = data.get("iterations", [])
    lines = [
        f"Function: {function_id}",
        f"Converged: {'yes' if converged else 'no'}",
        f"Iterations: {len(iterations)}",
    ]
    for it in iterations:
        idx = it.get("iteration", "?")
        score = it.get("score")
        score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
        lines.append(f"  #{idx}: score={score_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


@ralph_app.command("workspace")
def workspace(
    workflow_id: str = typer.Argument(help="Ralph Loop workflow ID"),
    function_id: str = typer.Option(..., "--function", "-f", help="Function ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List files in a Ralph Loop workspace for a specific function.

    Returns file paths and metadata in the workspace directory.
    """
    setup(output, quiet)
    data = api_get(
        f"/pipeline/ralph-loop/{workflow_id}/workspace",
        params={"function_id": function_id},
    )
    files = data.get("files", [])
    lines = [f"Workspace: {workflow_id} / {function_id}", f"Files ({len(files)}):"]
    for f in files:
        lines.append(f"  {f}" if isinstance(f, str) else f"  {f.get('path', f.get('name', '?'))}")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren ralph file {workflow_id} --function {function_id} --path <PATH>", "description": "Read a file"},
            {"command": f"ren ralph function {workflow_id} {function_id}", "description": "Function progress"},
        ],
        human_text="\n".join(lines),
    )


@ralph_app.command("file")
def file_read(
    workflow_id: str = typer.Argument(help="Ralph Loop workflow ID"),
    function_id: str = typer.Option(..., "--function", "-f", help="Function ID"),
    path: str = typer.Option(..., "--path", "-p", help="File path within workspace"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Read a single file from the Ralph Loop workspace.

    Returns file content. For text mode, prints the raw content.
    """
    setup(output, quiet)
    data = api_get(
        f"/pipeline/ralph-loop/{workflow_id}/workspace/file",
        params={"function_id": function_id, "path": path},
    )
    content = data.get("content", "")
    ok(
        result=data,
        next_actions=[
            {"command": f"ren ralph workspace {workflow_id} --function {function_id}", "description": "List all files"},
        ],
        human_text=f"--- {path} ---\n{content}",
    )
