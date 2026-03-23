"""Root Typer app and entrypoint."""

from __future__ import annotations

import typer

from renaissance_cli.commands.metrics import metrics_app
from renaissance_cli.commands.pipeline import pipeline_app
from renaissance_cli.commands.schedule import schedule_app
from renaissance_cli.commands.status import status
from renaissance_cli.commands.template import template_app

app = typer.Typer(
    name="ren",
    help="Renaissance CLI — control pipelines, schedules, and sims from any agent.",
    no_args_is_help=True,
)

app.add_typer(pipeline_app, name="pipeline")
app.add_typer(schedule_app, name="schedule")
app.add_typer(template_app, name="template")
app.add_typer(metrics_app, name="metrics")
app.command("status")(status)


def main_entrypoint() -> None:
    app()
