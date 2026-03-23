# Agent-Friendly CLI Design (Python/Typer)

> When building CLIs intended for AI agent consumption, apply these patterns.

---

## Stack

- **Framework**: Typer (type-hint based, auto `--help`)
- **Distribution**: `uv tool install git+https://github.com/...` (private repo OK, no PyPI needed)
- **Project setup**: `uv init --app --package my-cli` → `[project.scripts]` in pyproject.toml

---

## Output Contract

**All commands MUST support `--output json`.** Apply per-command, not as global callback (avoids flag-ordering issues).

```python
OutputOpt = typer.Option(None, "--output", "-o", help="text|json|jsonl", envvar="MYCLI_OUTPUT")
```

**Separation rule**: stdout = data only, stderr = logs/progress. Use `logging.StreamHandler(sys.stderr)`.

**Auto-detect**: If `not sys.stdout.isatty()`, default to JSON (piped context = agent context).

---

## Response Envelope

Every response follows this structure:

```json
{"ok": true, "result": {...}, "next_actions": [...]}
{"ok": false, "error": {"code": "AUTH_EXPIRED", "message": "...", "fix": "mycli auth login"}}
```

| Field | Purpose |
|-------|---------|
| `ok` | Boolean success flag — agents branch on this |
| `result` | Command output data |
| `next_actions` | HATEOAS — tells the agent what to do next (command + description) |
| `error.code` | Machine-parseable error identifier |
| `error.fix` | Actionable remediation command |

---

## HATEOAS `next_actions`

Include in every response. Agent follows these instead of consulting `--help`:

```python
ok(
    result={"deploy_id": "d-abc"},
    next_actions=[
        {"command": "mycli status d-abc", "description": "Check status"},
        {"command": "mycli rollback d-abc", "description": "Rollback if needed"},
    ],
)
```

---

## Three Discovery Layers

| When | Mechanism | Token cost | Provides |
|------|-----------|:----------:|----------|
| Before use | CLAUDE.md / AGENTS.md | ~50 | "This tool exists" |
| Before a command | `--help` | ~200-500 | Parameters, defaults, valid values |
| After a command | `next_actions` in response | ~100 | "Do this next" |

---

## Exit Codes

Document and keep stable across versions:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Usage error (bad arguments) |
| 3 | Auth failure |
| 4 | Not found |
| 5 | Conflict |
| 6 | Timeout |

---

## Non-Interactive Flags

Every command that might prompt MUST support:

```python
NoInputOpt = typer.Option(False, "--no-input", envvar="MYCLI_NO_INPUT")
YesOpt = typer.Option(False, "--yes", "-y")
QuietOpt = typer.Option(False, "--quiet", "-q")
```

---

## Composability

- **NDJSON** (`--output jsonl`): One JSON per line for streaming/piping
- **stdin**: Commands that accept piped input should read from stdin when `not sys.stdin.isatty()`
- **Idempotency**: Mutating commands support `--idempotency-key` or are inherently safe to retry
- **Dry-run**: Destructive commands support `--dry-run`

---

## Description Writing (docstrings + help=)

Docstring = command description in `--help`. Write for agents:

```python
@app.command()
def deploy(
    env: str = typer.Argument(help="Target: staging | production"),
    force: bool = typer.Option(False, "--force", help="Skip health check"),
):
    """Deploy app to target environment.

    Returns deploy_id. Use --output json for structured result.
    Requires: authenticated session (run 'mycli auth login' first).
    Side effects: rolling restart of target environment.
    """
```

Include: what it returns, prerequisites, side effects.

---

## MCP Wrapping

For agent frameworks that prefer MCP over CLI:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyCLI")

@mcp.tool()
def deploy(environment: str, force: bool = False) -> str:
    """Deploy to environment. Returns JSON with deploy_id."""
    result = subprocess.run(
        ["mycli", "deploy", environment, "--output", "json", "--no-input", "-y"]
        + (["--force"] if force else []),
        capture_output=True, text=True,
    )
    return result.stdout
```

---

*Sources: InfoQ "Patterns for AI Agent Driven CLIs" (2025), JoelClaw "CLI Design for AI Agents", Speakeasy "Making your CLI agent-friendly" (2026), clig.dev CLI Guidelines*
