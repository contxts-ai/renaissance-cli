"""ren capability — discover launchable capabilities and their schemas."""

from __future__ import annotations

import json

import typer

from renaissance_cli._client import api_get
from renaissance_cli._output import (
    OutputFormat,
    OutputOpt,
    QuietOpt,
    ok,
    setup,
)

capability_app = typer.Typer(
    name="capability",
    help="Discover launchable capabilities and their input schemas.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@capability_app.command("list")
def capability_list(
    kind: str = typer.Option(None, "--kind", "-k", help="Filter: template|workflow|agent"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """List all launchable capabilities (templates, workflows, agents).

    Returns name, kind, description, and launch endpoint for each.
    Requires: Trigger API running.
    """
    setup(output, quiet)
    params: dict = {}
    if kind:
        params["kind"] = kind
    data = api_get("/capabilities", params=params or None)
    caps = data.get("capabilities", [])

    # Group by kind for human display
    grouped: dict[str, list[dict]] = {}
    for c in caps:
        grouped.setdefault(c.get("kind", "other"), []).append(c)

    lines: list[str] = []
    for k in ("template", "workflow", "agent"):
        items = grouped.get(k, [])
        if not items:
            continue
        lines.append(f"\n{k.upper()}S ({len(items)}):")
        for item in items:
            name = item.get("name", "?")
            desc = item.get("description", "")[:60]
            lines.append(f"  {name:<30s} {desc}")

    ok(
        result=data,
        next_actions=[
            {"command": f"ren capability show {caps[0]['name']}", "description": "View schema"} if caps else
            {"command": "ren template list", "description": "Browse templates"},
        ],
        human_text="\n".join(lines) if lines else "No capabilities found.",
    )


# ---------------------------------------------------------------------------
# Show
# ---------------------------------------------------------------------------


@capability_app.command("show")
def capability_show(
    name: str = typer.Argument(help="Capability name"),
    output: OutputFormat = OutputOpt,
    quiet: bool = QuietOpt,
) -> None:
    """Show input schema for a capability.

    Returns JSON Schema, defaults, examples, and launch endpoint.
    """
    setup(output, quiet)
    data = api_get(f"/capabilities/{name}/schema")

    kind = data.get("kind", "?")
    endpoint = data.get("launch_endpoint", "?")
    schema = data.get("input_schema", {})
    defaults = data.get("defaults", {})
    examples = data.get("examples", [])

    lines = [
        f"Capability: {name} ({kind})",
        f"Launch endpoint: {endpoint}",
        "",
        "Input fields:",
    ]

    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    for field_name, field_def in props.items():
        ftype = field_def.get("type", "any")
        req = " (required)" if field_name in required else ""
        default = defaults.get(field_name)
        default_str = f" [default: {default}]" if default is not None else ""
        desc = field_def.get("description", "")
        lines.append(f"  {field_name}: {ftype}{req}{default_str}")
        if desc:
            lines.append(f"    {desc}")

    if examples:
        lines.append("\nExamples:")
        for ex in examples:
            lines.append(f"  {json.dumps(ex, ensure_ascii=False)}")

    na = [
        {"command": f"ren pipeline launch-dynamic {name} --json-str '{{\"target\": \"...\"}}'", "description": "Launch with JSON"},
    ]
    if kind == "agent":
        na.insert(0, {"command": f"ren agent run {name} --target ...", "description": "Run agent"})

    ok(result=data, next_actions=na, human_text="\n".join(lines))
