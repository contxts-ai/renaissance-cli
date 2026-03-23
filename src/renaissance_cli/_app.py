"""Root Typer app and entrypoint."""

from __future__ import annotations

import typer

from renaissance_cli.commands.agent import agent_app
from renaissance_cli.commands.ambient import ambient_app
from renaissance_cli.commands.artifact import artifact_app
from renaissance_cli.commands.auth import auth_app
from renaissance_cli.commands.capability import capability_app
from renaissance_cli.commands.doctor import doctor
from renaissance_cli.commands.eval import eval_app
from renaissance_cli.commands.execute import execute_app
from renaissance_cli.commands.metrics import metrics_app
from renaissance_cli.commands.pipeline import pipeline_app
from renaissance_cli.commands.ralph import ralph_app
from renaissance_cli.commands.schedule import schedule_app
from renaissance_cli.commands.service import service_app
from renaissance_cli.commands.status import status
from renaissance_cli.commands.template import template_app

app = typer.Typer(
    name="ren",
    help="Renaissance CLI — control pipelines, schedules, and sims from any agent.",
    no_args_is_help=True,
)

app.add_typer(agent_app, name="agent")
app.add_typer(ambient_app, name="ambient")
app.add_typer(artifact_app, name="artifact")
app.add_typer(auth_app, name="auth")
app.add_typer(capability_app, name="capability")
app.add_typer(eval_app, name="eval")
app.add_typer(execute_app, name="execute")
app.add_typer(metrics_app, name="metrics")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(ralph_app, name="ralph")
app.add_typer(schedule_app, name="schedule")
app.add_typer(service_app, name="service")
app.add_typer(template_app, name="template")
app.command("status")(status)
app.command("doctor")(doctor)


def main_entrypoint() -> None:
    app()
