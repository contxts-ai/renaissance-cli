"""ren execute — run prompts and workflows on Claude Server."""

from __future__ import annotations

import sys
import time

import httpx
import typer

from renaissance_cli._config import get_claude_server_url, get_trigger_api_key
from renaissance_cli._output import (
    ExitCode,
    OutputFormat,
    OutputOpt,
    QuietOpt,
    emit,
    fail,
    logger,
    ok,
    setup,
)

execute_app = typer.Typer(name="execute", help="Run prompts and workflows on Claude Server.", no_args_is_help=True)

TERMINAL_STATES = {"completed", "failed", "cancelled"}

# ---------------------------------------------------------------------------
# Claude Server HTTP client (separate from Trigger API client)
# ---------------------------------------------------------------------------

_claude_client: httpx.Client | None = None


def _get_claude_client() -> httpx.Client:
    global _claude_client
    if _claude_client is None:
        headers: dict[str, str] = {}
        api_key = get_trigger_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        _claude_client = httpx.Client(
            base_url=get_claude_server_url(), timeout=60.0, headers=headers,
        )
    return _claude_client


def _claude_post(path: str, body: dict) -> dict:
    try:
        r = _get_claude_client().post(path, json=body)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        url = get_claude_server_url()
        fail("CONNECTION_ERROR", f"Cannot reach Claude Server at {url}",
             fix=f"Run: ren auth login --claude-url <URL>  (current: {url})",
             exit_code=ExitCode.CONNECTION_ERROR)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        if status == 401:
            fail("AUTH_ERROR", "Authentication failed", fix="Run: ren auth login --key <KEY>", exit_code=ExitCode.AUTH_ERROR)
        else:
            fail("SERVER_ERROR", f"HTTP {status}: {detail}", exit_code=ExitCode.GENERAL_ERROR)
    return {}


def _claude_get(path: str) -> dict:
    try:
        r = _get_claude_client().get(path)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        url = get_claude_server_url()
        fail("CONNECTION_ERROR", f"Cannot reach Claude Server at {url}",
             fix=f"Run: ren auth login --claude-url <URL>  (current: {url})",
             exit_code=ExitCode.CONNECTION_ERROR)
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        fail("SERVER_ERROR", f"HTTP {exc.response.status_code}: {detail}", exit_code=ExitCode.GENERAL_ERROR)
    return {}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@execute_app.command("prompt")
def execute_prompt(
    prompt: str = typer.Argument(help="Prompt to send to Claude"),
    system_prompt: str = typer.Option(None, "--system", "-s", help="System prompt for context"),
    model: str = typer.Option(None, "--model", "-m", help="Model override (e.g. claude-sonnet-4-5-20250514)"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion and return result"),
    interval: int = typer.Option(3, "--interval", help="Poll interval in seconds (with --wait)"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Execute a prompt on Claude Server.

    Returns a task_id for tracking. Use --wait to block until completion.
    Side effects: starts a Claude execution task on the server.
    """
    setup(output, quiet)
    body: dict = {"prompt": prompt}
    if system_prompt:
        body["system_prompt"] = system_prompt
    if model:
        body["model"] = model

    logger.info("Executing prompt on Claude Server...")
    data = _claude_post("/execute", body)
    task_id = data.get("task_id", "unknown")

    if not wait:
        ok(
            result=data,
            next_actions=[
                {"command": f"ren execute status {task_id}", "description": "Check task status"},
                {"command": f"ren execute status {task_id} --wait", "description": "Wait for result"},
            ],
            human_text=f"Task created: {task_id}",
        )
        return

    # Wait mode: poll until terminal state
    while True:
        status_data = _claude_get(f"/execute/{task_id}")
        task_status = status_data.get("status", "unknown")

        if task_status in TERMINAL_STATES:
            result_text = status_data.get("result_text") or status_data.get("structured_output")
            ok(
                result=status_data,
                next_actions=[
                    {"command": "ren execute prompt '...'", "description": "Run another prompt"},
                ],
                human_text=f"Task {task_id}: {task_status}\n{result_text or '(no output)'}",
            )
            return

        if not quiet:
            logger.info("Task %s: %s ...", task_id, task_status)
        time.sleep(interval)


@execute_app.command("status")
def execute_status(
    task_id: str = typer.Argument(help="Task ID from execute prompt"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
    interval: int = typer.Option(3, "--interval", help="Poll interval in seconds"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Check status of a Claude Server execution task.

    Returns task status, result text, and structured output if available.
    """
    setup(output, quiet)

    if not wait:
        data = _claude_get(f"/execute/{task_id}")
        task_status = data.get("status", "unknown")
        na = [{"command": f"ren execute status {task_id} --wait", "description": "Wait for result"}] if task_status not in TERMINAL_STATES else []
        ok(result=data, next_actions=na,
           human_text=f"Task {task_id}: {task_status}")
        return

    while True:
        data = _claude_get(f"/execute/{task_id}")
        task_status = data.get("status", "unknown")
        if task_status in TERMINAL_STATES:
            result_text = data.get("result_text") or data.get("structured_output")
            ok(result=data,
               human_text=f"Task {task_id}: {task_status}\n{result_text or '(no output)'}")
            return
        if not quiet:
            logger.info("Task %s: %s ...", task_id, task_status)
        time.sleep(interval)
