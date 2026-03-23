"""ren auth — configure API credentials."""

from __future__ import annotations

import os

import typer

from renaissance_cli._config import (
    CONFIG_FILE,
    get_claude_server_url,
    get_trigger_api_key,
    get_trigger_url,
    save_config,
)
from renaissance_cli._output import OutputFormat, OutputOpt, QuietOpt, ok, setup

auth_app = typer.Typer(name="auth", help="Configure API credentials for Trigger and Claude Server.", no_args_is_help=True)


@auth_app.command("login")
def auth_login(
    trigger_url: str = typer.Option(None, "--trigger-url", help="Trigger API URL (e.g. https://trigger.renaissance.financial)"),
    claude_url: str = typer.Option(None, "--claude-url", help="Claude Server URL (e.g. https://claude-server.renaissance.financial)"),
    key: str = typer.Option(None, "--key", help="API key (shared by both services)"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Save API credentials to ~/.config/renaissance/cli.json.

    Precedence: env vars > config file > defaults.
    Credentials are stored locally and only sent to the configured APIs.
    """
    setup(output, quiet)
    updates: dict = {}
    if trigger_url:
        updates["trigger_url"] = trigger_url
    if claude_url:
        updates["claude_server_url"] = claude_url
    if key:
        updates["trigger_api_key"] = key

    if not updates:
        typer.echo("Provide at least one of --trigger-url, --claude-url, or --key. Example:")
        typer.echo("  ren auth login \\")
        typer.echo("    --trigger-url https://trigger.renaissance.financial \\")
        typer.echo("    --claude-url https://claude-server.renaissance.financial \\")
        typer.echo("    --key <API_KEY>")
        raise typer.Exit(2)

    save_config(updates)
    ok(
        result={"config_file": str(CONFIG_FILE), "updated": list(updates.keys())},
        next_actions=[
            {"command": "ren auth status", "description": "Verify configuration"},
            {"command": "ren status", "description": "Check system health"},
        ],
        human_text=f"Credentials saved to {CONFIG_FILE}",
    )


def _source(env_key: str, value: str, default: str) -> str:
    if os.getenv(env_key):
        return "env"
    if value != default:
        return "config"
    return "default"


def _mask(secret: str) -> str:
    if len(secret) > 4:
        return f"{secret[:4]}{'*' * (len(secret) - 4)}"
    return "(set)" if secret else "(not set)"


@auth_app.command("status")
def auth_status(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show current configuration and source of each value."""
    setup(output, quiet)

    t_url = get_trigger_url()
    c_url = get_claude_server_url()
    key = get_trigger_api_key()

    ok(
        result={
            "trigger_url": {"value": t_url, "source": _source("TRIGGER_URL", t_url, "http://localhost:58100")},
            "claude_server_url": {"value": c_url, "source": _source("CLAUDE_SERVER_URL", c_url, "http://localhost:58000")},
            "trigger_api_key": {"value": _mask(key), "source": _source("TRIGGER_API_KEY", key, "")},
            "config_file": str(CONFIG_FILE),
        },
        next_actions=[
            {"command": "ren auth login --trigger-url <URL> --claude-url <URL> --key <KEY>", "description": "Update credentials"},
            {"command": "ren status", "description": "Test connection"},
        ],
        human_text=f"Trigger URL:       {t_url} (from {_source('TRIGGER_URL', t_url, 'http://localhost:58100')})\n"
                   f"Claude Server URL: {c_url} (from {_source('CLAUDE_SERVER_URL', c_url, 'http://localhost:58000')})\n"
                   f"API Key:           {_mask(key)} (from {_source('TRIGGER_API_KEY', key, '')})\n"
                   f"Config file:       {CONFIG_FILE}",
    )


@auth_app.command("logout")
def auth_logout(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Remove saved credentials from config file."""
    setup(output, quiet)
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        ok(
            result={"deleted": str(CONFIG_FILE)},
            next_actions=[
                {"command": "ren auth login --trigger-url <URL> --key <KEY>", "description": "Re-authenticate"},
            ],
            human_text=f"Credentials removed: {CONFIG_FILE}",
        )
    else:
        ok(result={"message": "No config file found"}, human_text="No credentials to remove.")
