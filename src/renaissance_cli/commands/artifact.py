"""ren artifact — browse and read workflow artifacts."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_get
from renaissance_cli._output import (
    ExitCode,
    OutputFormat,
    OutputOpt,
    QuietOpt,
    fail,
    ok,
    setup,
)

artifact_app = typer.Typer(
    name="artifact",
    help="Browse and read workflow artifacts.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@artifact_app.command("list")
def artifact_list(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List all artifacts for a workflow.

    Returns artifact name, type (file|output), and fetch endpoint.
    Detects workflow type automatically.
    """
    setup(output, quiet)
    data = api_get(f"/artifacts/{workflow_id}")
    artifacts = data.get("artifacts", [])

    lines = [f"Artifacts for {workflow_id} ({len(artifacts)}):"]
    for a in artifacts:
        atype = a.get("type", "?")
        name = a.get("name", "?")
        size = a.get("size")
        size_str = f"  ({size:,} bytes)" if size is not None else ""
        lines.append(f"  [{atype}] {name}{size_str}")

    na: list[dict] = []
    if artifacts:
        first = artifacts[0]
        ref = first.get("name", first.get("step_id", first.get("function_id", "?")))
        na.append({"command": f"ren artifact get {workflow_id} {ref}", "description": "Read first artifact"})
    na.append({"command": f"ren pipeline progress {workflow_id}", "description": "Pipeline progress"})

    ok(result=data, next_actions=na, human_text="\n".join(lines))


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@artifact_app.command("get")
def artifact_get(
    workflow_id: str = typer.Argument(help="Workflow ID"),
    ref: str = typer.Argument(help="Artifact reference (file path or step ID from 'artifact list')"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Read an artifact by reference.

    Looks up the artifact in the list to find its fetch endpoint,
    then retrieves the content. Use 'ren artifact list' first to see
    available artifacts and their references.
    """
    setup(output, quiet)

    # 1. Fetch artifact list to find the fetch_endpoint
    list_data = api_get(f"/artifacts/{workflow_id}")
    artifacts = list_data.get("artifacts", [])

    # 2. Match ref against name, step_id, function_id, or path
    fetch_endpoint = None
    for a in artifacts:
        if ref in (a.get("name"), a.get("step_id"), a.get("function_id"), a.get("path")):
            fetch_endpoint = a.get("fetch_endpoint")
            break

    if not fetch_endpoint:
        fail(
            "NOT_FOUND",
            f"Artifact '{ref}' not found in {workflow_id}. Use 'ren artifact list {workflow_id}' to see available artifacts.",
            exit_code=ExitCode.NOT_FOUND,
        )
        return

    # 3. Fetch the artifact content
    data = api_get(fetch_endpoint)
    content = data.get("content", data.get("output", ""))

    if isinstance(content, str):
        text = content[:3000]
        if len(content) > 3000:
            text += f"\n... ({len(content)} chars total)"
    elif isinstance(content, dict):
        import json
        text = json.dumps(content, indent=2, ensure_ascii=False)[:3000]
    else:
        text = str(content)[:3000]

    ok(
        result=data,
        next_actions=[
            {"command": f"ren artifact list {workflow_id}", "description": "List all artifacts"},
        ],
        human_text=text,
    )
