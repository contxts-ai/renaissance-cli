"""``ren research`` — thin HTTP wrapper over PB Trigger's ``/research/*`` endpoints.

Transport for the mission_control research harness (see ADR-001 + the plan at
renaissance_mission_control/docs/plans/research-harness-textual-tui.md). Every
command maps 1:1 to one HTTP call; envelope passthrough. Mutating endpoints
send ``Idempotency-Key`` via HTTP header (per plan §"HTTP Transport Layer");
PB's body-level ``idempotency_key`` field is an accepted fallback but not
used by this client. Human mode prints concise summaries; json mode returns
the full envelope.
"""

from __future__ import annotations

from pathlib import Path

import typer

import json
import sys

from renaissance_cli._client import api_get, api_post
from renaissance_cli._output import (
    ExitCode,
    OutputFormat,
    OutputOpt,
    QuietOpt,
    _resolve_format,
    emit,
    fail,
    logger,
    ok,
    setup,
)

research_app = typer.Typer(
    name="research",
    help="Drive the mission_control research harness via PB Trigger.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Common options
# ---------------------------------------------------------------------------


TaskOpt = typer.Option(..., "--task", "-t", help="Research task id (e.g. rq-oracle-lag)")
RunIdOpt = typer.Option(None, "--run-id", help="Specific run id (omitted → latest)")
IdemOpt = typer.Option(
    None, "--idempotency-key",
    help="Stable key for retry-safe mutations",
    envvar="REN_RESEARCH_IDEMPOTENCY_KEY",
)


def _rpath(task: str, suffix: str, run_id: str | None = None) -> str:
    """Build /research/runs/{task}{suffix} with optional ?run_id=..."""
    path = f"/research/runs/{task}{suffix}"
    if run_id:
        path = f"{path}?run_id={run_id}"
    return path


def _idem_headers(idempotency_key: str | None) -> dict[str, str] | None:
    """Return ``{"Idempotency-Key": key}`` or ``None`` if no key.

    Per plan §"HTTP Transport Layer", mutating endpoints use the header
    transport. Omitting the key means no idempotency tracking (still safe
    for single-shot invocations).
    """
    if idempotency_key:
        return {"Idempotency-Key": idempotency_key}
    return None


def _result(env: dict) -> dict:
    """Extract ``result`` from a {ok, result, ...} envelope, failing on ok=false.

    PB's HTTPException wraps our envelope in {"detail": {...envelope}} on error.
    ``_client`` already translated non-2xx to ``fail()``, so we only see 2xx here.
    """
    if not env.get("ok", True):
        err = env.get("error") or {}
        fail(err.get("code", "UNKNOWN"), err.get("message", "unknown error"),
             fix=err.get("fix"), exit_code=ExitCode.GENERAL_ERROR)
    return env.get("result") or {}


def _print_envelope_passthrough(env: dict, human_text: str | None = None) -> None:
    """Forward PB's envelope through ren's emit so next_actions survive."""
    result = _result(env)
    next_actions = env.get("next_actions") or []
    ok(result=result, next_actions=next_actions, human_text=human_text)


def _print_streaming_passthrough(
    env: dict,
    human_text: str | None = None,
) -> None:
    """Stream a list-shaped ``result`` as one JSON per line in jsonl mode.

    Behavior by output format:
    - ``jsonl`` and ``result`` is a list  → one JSON per line (no envelope).
    - ``jsonl`` and ``result`` is a dict  → falls back to envelope-on-one-line.
    - ``json``                            → full envelope (single object).
    - ``text``                            → human_text or pretty-printed envelope.

    Use this for surfaces the plan §"Output contract" calls out as streaming:
    ``timeline``, ``traces``, ``runs list``, ``artifacts list``.
    """
    result = _result(env)
    fmt = _resolve_format(None)
    if fmt == OutputFormat.jsonl and isinstance(result, list):
        for item in result:
            json.dump(item, sys.stdout, ensure_ascii=False)
            print()
        sys.stdout.flush()
        return
    next_actions = env.get("next_actions") or []
    ok(result=result, next_actions=next_actions, human_text=human_text)


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


@research_app.command("submit")
def submit(
    task: str = TaskOpt,
    market: str = typer.Option(..., "--market", "-m", help="Morpho Blue market id"),
    question: str = typer.Option(..., "--question", "-q", help="Research question"),
    max_iterations: int = typer.Option(10, "--max-iterations"),
    idempotency_key: str = IdemOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Submit a new research run as a durable Temporal workflow.

    Returns: {workflow_id, task_id, run_id, market_id}.
    Prerequisites: no RUNNING workflow for this task.
    """
    setup(output, quiet)
    logger.info("Submitting research run: task=%s market=%s", task, market)
    body = {
        "task_id": task,
        "market_id": market,
        "question": question,
        "max_iterations": max_iterations,
    }
    env = api_post("/research/runs", body, headers=_idem_headers(idempotency_key))
    _print_envelope_passthrough(
        env, human_text=f"Submitted {task} → {_result(env).get('workflow_id')}"
    )


@research_app.command("submit-phase")
def submit_phase(
    phase: str = typer.Argument(..., help="Currently only 'collect' supported"),
    task: str = TaskOpt,
    plan: Path = typer.Option(..., "--plan", help="Path to local CollectionPlan JSON"),
    run_id: str = RunIdOpt,
    idempotency_key: str = IdemOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Start a one-shot phase workflow (collection only today).

    Inlines the plan JSON into the POST body (5 MB cap per request doc).
    """
    setup(output, quiet)
    if phase != "collect":
        fail("UNSUPPORTED_PHASE", f"submit-phase only supports 'collect' today, got {phase!r}",
             exit_code=ExitCode.USAGE_ERROR)
    if not plan.exists():
        fail("PLAN_NOT_FOUND", f"plan file not found: {plan}",
             exit_code=ExitCode.NOT_FOUND)
    try:
        import json as _json
        plan_payload = _json.loads(plan.read_text())
    except Exception as exc:
        fail("INVALID_PLAN_JSON", f"plan is not valid JSON: {exc}",
             exit_code=ExitCode.USAGE_ERROR)
        return
    body: dict = {"plan": plan_payload}
    if run_id:
        body["run_id"] = run_id
    env = api_post(
        f"/research/runs/{task}/phases/collect", body,
        headers=_idem_headers(idempotency_key),
    )
    _print_envelope_passthrough(env)


# ---------------------------------------------------------------------------
# Inspect / read
# ---------------------------------------------------------------------------


@research_app.command("status")
def status(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show task's current state, next phase, workflow status."""
    setup(output, quiet)
    env = api_get(_rpath(task, "/state", run_id))
    r = _result(env)
    human = (
        f"task={task} run={r.get('run_id')} state={r.get('current_state')} "
        f"next={r.get('next_phase')} wf={r.get('workflow_id')} "
        f"wf_status={r.get('workflow_status')}"
    )
    _print_envelope_passthrough(env, human_text=human)


@research_app.command("pending")
def pending(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Read pending-gate with provenance (workflow / state_fallback / disk_only / none)."""
    setup(output, quiet)
    env = api_get(_rpath(task, "/pending", run_id))
    _print_envelope_passthrough(env)


@research_app.command("show")
def show(
    key: str = typer.Argument(..., help="Artifact key (hypothesis_set, collection_plan, ...)"),
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    raw: bool = typer.Option(False, "--raw", help="Include envelope, not just payload"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Print an artifact payload from a run."""
    setup(output, quiet)
    params: list[str] = []
    if run_id:
        params.append(f"run_id={run_id}")
    if raw:
        params.append("raw=true")
    qs = ("?" + "&".join(params)) if params else ""
    env = api_get(f"/research/runs/{task}/artifacts/{key}{qs}")
    _print_envelope_passthrough(env)


@research_app.command("review")
def review(
    phase: str = typer.Argument(..., help="hypothesis | collection | eda | mechanism | validation | decision"),
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Bundle the gate's primary artifact, critique, and recent events."""
    setup(output, quiet)
    env = api_get(_rpath(task, f"/review/{phase}", run_id))
    r = _result(env)
    human = (
        f"phase={phase} completeness={r.get('completeness')} "
        f"recommended={r.get('recommended_action')}"
    )
    _print_envelope_passthrough(env, human_text=human)


@research_app.command("timeline")
def timeline(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    limit: int = typer.Option(200, "--limit"),
    phase: str = typer.Option(None, "--phase"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Print recent run events (newest last).

    Output: ``--output jsonl`` streams one event per line (NDJSON);
    ``--output json`` returns the full envelope; default text mode
    pretty-prints. Use jsonl when piping to ``jq`` or another consumer.
    """
    setup(output, quiet)
    params = [f"limit={limit}"]
    if run_id:
        params.append(f"run_id={run_id}")
    if phase:
        params.append(f"phase={phase}")
    env = api_get(f"/research/runs/{task}/timeline?" + "&".join(params))
    _print_streaming_passthrough(env)


@research_app.command("runs")
def runs_list(
    task: str = TaskOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Enumerate all runs for a task.

    Output: ``--output jsonl`` streams one run summary per line; otherwise
    returns the full envelope.
    """
    setup(output, quiet)
    env = api_get(f"/research/tasks/{task}/runs")
    _print_streaming_passthrough(env)


# ---------------------------------------------------------------------------
# Mutations (Temporal-only)
# ---------------------------------------------------------------------------


@research_app.command("approve")
def approve(
    task: str = TaskOpt,
    note: str = typer.Option("", "--note"),
    idempotency_key: str = IdemOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Approve the current pending gate (collection or eda_warn)."""
    setup(output, quiet)
    env = api_post(
        f"/research/runs/{task}/approve", {"note": note},
        headers=_idem_headers(idempotency_key),
    )
    _print_envelope_passthrough(env)


@research_app.command("reject")
def reject(
    task: str = TaskOpt,
    reason: str = typer.Option(..., "--reason"),
    idempotency_key: str = IdemOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Reject the current collection gate with a reason."""
    setup(output, quiet)
    env = api_post(
        f"/research/runs/{task}/reject", {"reason": reason},
        headers=_idem_headers(idempotency_key),
    )
    _print_envelope_passthrough(env)


@research_app.command("park")
def park(
    task: str = TaskOpt,
    reason: str = typer.Option(..., "--reason"),
    idempotency_key: str = IdemOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Park the workflow at the next safe point."""
    setup(output, quiet)
    env = api_post(
        f"/research/runs/{task}/park", {"reason": reason},
        headers=_idem_headers(idempotency_key),
    )
    _print_envelope_passthrough(env)


@research_app.command("advance")
def advance(
    task: str = TaskOpt,
    idempotency_key: str = IdemOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Generic unblock: approve pending gate if one exists, else no-op."""
    setup(output, quiet)
    env = api_post(
        f"/research/runs/{task}/advance", {},
        headers=_idem_headers(idempotency_key),
    )
    _print_envelope_passthrough(env)


# ---------------------------------------------------------------------------
# Extended read surface — traces / artifacts-list / notebook / explain / resume
# ---------------------------------------------------------------------------


@research_app.command("artifacts-list")
def artifacts_list(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    phase: str = typer.Option(None, "--phase", help="Filter by stage/phase"),
    all_keys: bool = typer.Option(False, "--all", help="Include keys not present on disk"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Enumerate artifacts in a run (default: present-only, all phases).

    Output: ``--output jsonl`` streams one record per line; otherwise full envelope.
    """
    setup(output, quiet)
    params: list[str] = []
    if run_id:
        params.append(f"run_id={run_id}")
    if phase:
        params.append(f"phase={phase}")
    if all_keys:
        params.append("present_only=false")
    qs = ("?" + "&".join(params)) if params else ""
    env = api_get(f"/research/runs/{task}/artifacts{qs}")
    _print_streaming_passthrough(env)


@research_app.command("traces")
def traces(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Per-phase trace summary (tool calls, LLM calls, tokens, cost)."""
    setup(output, quiet)
    env = api_get(_rpath(task, "/traces", run_id))
    _print_envelope_passthrough(env)


@research_app.command("notebook")
def notebook(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    section: str = typer.Option(None, "--section", help="Filter to a single section"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Fetch the run's ExperimentNotebook."""
    setup(output, quiet)
    params: list[str] = []
    if run_id:
        params.append(f"run_id={run_id}")
    if section:
        params.append(f"section={section}")
    qs = ("?" + "&".join(params)) if params else ""
    env = api_get(f"/research/runs/{task}/notebook{qs}")
    _print_envelope_passthrough(env)


@research_app.command("explain")
def explain(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """LLM-synthesized 'why here' digest for the run."""
    setup(output, quiet)
    env = api_get(_rpath(task, "/explain", run_id))
    _print_envelope_passthrough(env)


@research_app.command("resume")
def resume(
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Diagnostic: compute the next phase a local run would execute (no mutation)."""
    setup(output, quiet)
    env = api_get(_rpath(task, "/resume", run_id))
    _print_envelope_passthrough(env)


@research_app.command("runs-latest")
def runs_latest(
    task: str = TaskOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Return the latest run summary for a task."""
    setup(output, quiet)
    env = api_get(f"/research/tasks/{task}/runs/latest")
    _print_envelope_passthrough(env)


# ---------------------------------------------------------------------------
# forward-memory (market-scoped, not task-scoped)
# ---------------------------------------------------------------------------


forward_memory_app = typer.Typer(
    name="forward-memory",
    help="Read cross-run hypothesis forward memory for a market.",
    no_args_is_help=True,
)


@forward_memory_app.command("show")
def forward_memory_show(
    market: str = typer.Option(..., "--market", "-m", help="Morpho Blue market id"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Return the merged forward-memory snapshot for a market."""
    setup(output, quiet)
    env = api_get(f"/research/markets/{market}/forward-memory")
    _print_envelope_passthrough(env)


research_app.add_typer(forward_memory_app, name="forward-memory")


# ---------------------------------------------------------------------------
# Low-level escape hatches: signal / query / doctor
# ---------------------------------------------------------------------------


@research_app.command("signal")
def signal(
    signal_name: str = typer.Argument(..., help="Raw Temporal signal name"),
    value: str = typer.Argument("", help="Optional free-form value"),
    task: str = TaskOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Send a raw signal to the workflow (no idempotency; use approve/reject for gates)."""
    setup(output, quiet)
    env = api_post(
        f"/research/runs/{task}/signal",
        {"signal_name": signal_name, "value": value},
    )
    _print_envelope_passthrough(env)


@research_app.command("query")
def query(
    selector: str = typer.Argument(
        ..., help="status | stage | pending-approval | artifacts | next-actions",
    ),
    task: str = TaskOpt,
    run_id: str = RunIdOpt,
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Run a named workflow query (raw selector → raw result)."""
    setup(output, quiet)
    path = f"/research/runs/{task}/query/{selector}"
    if run_id:
        path = f"{path}?run_id={run_id}"
    env = api_get(path)
    _print_envelope_passthrough(env)


@research_app.command("doctor")
def doctor(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Probe whether the PB Trigger has the mission_control backend installed."""
    setup(output, quiet)
    env = api_get("/research/doctor")
    _print_envelope_passthrough(env)


# Silence unused import for linters — emit is re-exported for future SSE work.
_ = emit
