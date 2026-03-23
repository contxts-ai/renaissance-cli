"""ren template — discover available pipeline templates."""

from __future__ import annotations

import typer

from renaissance_cli._client import api_get
from renaissance_cli._output import OutputFormat, OutputOpt, QuietOpt, ok, setup

template_app = typer.Typer(name="template", help="Discover pipeline templates.", no_args_is_help=True)


@template_app.command("list")
def template_list(
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List all available pipeline templates.

    Returns template names, step counts, and descriptions.
    """
    setup(output, quiet)
    data = api_get("/pipelines/templates")
    templates = data.get("templates", [])
    names = [t.get("name", "?") for t in templates]
    ok(
        result=data,
        next_actions=[
            {"command": f"ren template show {names[0]}", "description": "View template details"} if names else
            {"command": "ren status", "description": "Check system status"},
        ],
        human_text="\n".join(
            f"  {t.get('name', '?'):30s} ({t.get('step_count', '?')} steps) {t.get('description', '')}"
            for t in templates
        ) or "No templates found.",
    )


@template_app.command("show")
def template_show(
    name: str = typer.Argument(help="Template name"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show template details including steps and configuration.

    Returns the full template blueprint with step definitions and dependencies.
    """
    setup(output, quiet)
    data = api_get(f"/pipelines/templates/{name}/detail")
    steps = data.get("steps", [])
    ok(
        result=data,
        next_actions=[
            {"command": f"ren pipeline launch --template {name} --target <TARGET>", "description": "Launch this template"},
            {"command": "ren template list", "description": "Back to template list"},
        ],
        human_text=f"Template: {name} ({len(steps)} steps)\n" + "\n".join(
            f"  {i+1}. {s.get('id', '?')} — {s.get('command', '?')}"
            for i, s in enumerate(steps)
        ),
    )
