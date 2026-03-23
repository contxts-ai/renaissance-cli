"""ren eval — trigger and inspect online evaluations."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_get, api_post
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    logger,
    ok,
    setup,
)

eval_app = typer.Typer(
    name="eval",
    help="Trigger and inspect online skill evaluations.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


@eval_app.command("trigger")
def trigger(
    skill: str = typer.Option(..., "--skill", "-s", help="Skill name to evaluate"),
    request: str = typer.Option(None, "--request", "-r", help="Input request text"),
    output_text: str = typer.Option(None, "--output-text", help="Skill output text to evaluate"),
    mode: str = typer.Option("skill", "--mode", "-m", help="Execution mode: skill|agent"),
    timeout: int = typer.Option(3600, "--timeout", help="Timeout in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Trigger an online evaluation for a skill.

    Starts an eval workflow and returns the eval_id for tracking.
    Side effects: creates an OnlineSkillEvalWorkflow in Temporal.
    """
    setup(output, quiet)
    body: dict = {
        "skill_name": skill,
        "execution_mode": mode,
        "timeout_seconds": timeout,
    }
    if request is not None:
        body["request"] = request
    if output_text is not None:
        body["output"] = output_text

    logger.info("Triggering eval for skill=%s mode=%s", skill, mode)
    data = api_post("/trigger", body)
    eval_id = data.get("eval_id", data.get("workflow_id", "unknown"))

    ok(
        result=data,
        next_actions=[
            {"command": f"ren eval detail {eval_id}", "description": "View eval result"},
            {"command": f"ren eval result {eval_id}", "description": "Check workflow status"},
        ],
        human_text=f"Eval triggered: {eval_id}",
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@eval_app.command("detail")
def detail(
    eval_id: str = typer.Argument(help="Eval ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show full eval result with scorer details.

    Returns per-scorer scores, reasoning, and metadata.
    """
    setup(output, quiet)
    data = api_get(f"/eval/{eval_id}/detail")

    scores = data.get("scores", data.get("scorer_results", []))
    lines = [f"Eval: {eval_id}", f"Status: {data.get('status', '?')}"]
    if isinstance(scores, list):
        for s in scores:
            scorer = s.get("scorer", s.get("name", "?"))
            score = s.get("score", "?")
            lines.append(f"  {scorer:<30s} {score}")
    elif isinstance(scores, dict):
        for scorer, score in scores.items():
            lines.append(f"  {scorer:<30s} {score}")

    ok(
        result=data,
        next_actions=[
            {"command": "ren eval trigger --skill <SKILL>", "description": "Run another eval"},
        ],
        human_text="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# Result (generic workflow result)
# ---------------------------------------------------------------------------


@eval_app.command("result")
def result(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Query any workflow result by ID.

    Returns status and output for completed workflows.
    """
    setup(output, quiet)
    data = api_get(f"/result/{workflow_id}")
    status = data.get("status", "unknown")

    na: list[dict] = []
    if status not in {"completed", "failed", "cancelled"}:
        na.append({"command": f"ren eval result {workflow_id}", "description": "Check again"})

    ok(result=data, next_actions=na, human_text=f"[{workflow_id}] {status}")
