"""Agent-friendly output helpers: envelope, emit, exit codes."""

from __future__ import annotations

import json
import logging
import sys
from enum import Enum, IntEnum

import typer

logger = logging.getLogger("ren")
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)


class OutputFormat(str, Enum):
    text = "text"
    json = "json"
    jsonl = "jsonl"


class ExitCode(IntEnum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    USAGE_ERROR = 2
    AUTH_ERROR = 3
    NOT_FOUND = 4
    CONFLICT = 5
    TIMEOUT = 6
    CONNECTION_ERROR = 7


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_output_format = OutputFormat.text


def _resolve_format(fmt: OutputFormat | None) -> OutputFormat:
    if fmt is not None:
        return fmt
    return _output_format


def setup(output: OutputFormat | None, quiet: bool) -> None:
    """Apply shared options. Call at the start of every command."""
    global _output_format
    if output is not None:
        _output_format = output
    if quiet:
        logger.setLevel(logging.WARNING)
    if not sys.stdout.isatty() and _output_format == OutputFormat.text:
        _output_format = OutputFormat.json


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------


def emit(data: dict, human_text: str | None = None, fmt: OutputFormat | None = None) -> None:
    f = _resolve_format(fmt)
    if f == OutputFormat.json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    elif f == OutputFormat.jsonl:
        json.dump(data, sys.stdout, ensure_ascii=False)
        print()
        sys.stdout.flush()
    else:
        typer.echo(human_text or json.dumps(data, indent=2, ensure_ascii=False))


def ok(
    result: dict,
    next_actions: list[dict] | None = None,
    human_text: str | None = None,
) -> None:
    envelope: dict = {"ok": True, "result": result}
    if next_actions:
        envelope["next_actions"] = next_actions
    emit(envelope, human_text=human_text)


def fail(
    code: str,
    message: str,
    fix: str | None = None,
    exit_code: ExitCode = ExitCode.GENERAL_ERROR,
) -> None:
    envelope: dict = {"ok": False, "error": {"code": code, "message": message}}
    if fix:
        envelope["error"]["fix"] = fix
    emit(envelope, human_text=f"Error [{code}]: {message}")
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# Shared options (per-command)
# ---------------------------------------------------------------------------

OutputOpt = typer.Option(None, "--output", "-o", help="Output format: text|json|jsonl", envvar="REN_OUTPUT")
QuietOpt = typer.Option(False, "--quiet", "-q", help="Suppress progress output")
YesOpt = typer.Option(False, "--yes", "-y", help="Auto-confirm destructive ops")
