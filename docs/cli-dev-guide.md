# CLI Development Guide (Typer + uv)

> Practical reference for building and distributing Python CLIs.

---

## Project Setup

```bash
uv init --app --package my-cli        # scaffold
uv add typer rich                      # core deps
uv run my-cli                          # run during dev
```

### Minimum pyproject.toml

```toml
[project]
name = "my-cli"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["typer>=0.24", "rich>=14"]

[project.scripts]
my-cli = "my_cli:main_entrypoint"      # ← console entry point

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Directory Structure

```
my-cli/
├── pyproject.toml
├── src/my_cli/
│   ├── __init__.py      # app = typer.Typer(), def main_entrypoint(): app()
│   └── commands/        # optional: split commands into modules
└── uv.lock
```

---

## Distribution (Private GitHub Repo)

No PyPI registration needed. GitHub repo = distribution channel.

### Install

```bash
# HTTPS (uses GITHUB_TOKEN or gh auth)
uv tool install git+https://github.com/USER/REPO.git

# SSH
uv tool install git+ssh://git@github.com/USER/REPO.git

# Specific tag
uv tool install git+https://github.com/USER/REPO.git@v1.0.0

# Specific branch
uv tool install git+https://github.com/USER/REPO.git@main
```

### Manage

```bash
uv tool upgrade my-cli                # upgrade to latest
uv tool uninstall my-cli              # remove
uv tool list                          # see all installed tools
uvx my-cli                            # run without permanent install
```

### CI/CD Release (optional)

```yaml
# .github/workflows/release.yml
on:
  push:
    tags: ['v*']
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
```

---

## Typer Patterns

### Command Structure

```python
import typer

app = typer.Typer(name="my-cli", help="What this CLI does.", no_args_is_help=True)

# Simple command
@app.command()
def hello(name: str = typer.Argument("world", help="Who to greet")):
    """Greet someone."""
    typer.echo(f"Hello, {name}!")

# Command groups (noun-verb pattern)
deploy_app = typer.Typer(help="Manage deployments")
app.add_typer(deploy_app, name="deploy")

@deploy_app.command("create")
def deploy_create(env: str = typer.Argument(help="staging | production")):
    """Create a new deployment."""
    ...

@deploy_app.command("status")
def deploy_status(deploy_id: str = typer.Argument(help="Deployment ID")):
    """Check deployment status."""
    ...

# → my-cli deploy create staging
# → my-cli deploy status d-abc123
```

### Arguments vs Options

```python
@app.command()
def fetch(
    # Argument — positional, required by default
    url: str = typer.Argument(help="URL to fetch"),

    # Option — named, optional by default
    timeout: int = typer.Option(10, "--timeout", "-t", help="Seconds"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip cache"),

    # Enum option — Typer validates automatically
    output: OutputFormat = typer.Option(None, "--output", "-o"),

    # Environment variable fallback
    token: str = typer.Option(None, envvar="MYCLI_TOKEN"),
):
    ...
```

### Shared Options (per-command, not global callback)

```python
# Define once, reuse across commands
OutputOpt = typer.Option(None, "--output", "-o", help="text|json|jsonl", envvar="MYCLI_OUTPUT")
QuietOpt = typer.Option(False, "--quiet", "-q", help="Suppress progress")

@app.command()
def cmd_a(output: OutputFormat = OutputOpt, quiet: bool = QuietOpt):
    ...

@app.command()
def cmd_b(output: OutputFormat = OutputOpt, quiet: bool = QuietOpt):
    ...
```

**IMPORTANT**: Prefer per-command options over `@app.callback()` global options. Global callback options must come BEFORE the subcommand (`my-cli -o json hello`), which confuses agents. Per-command options work after the subcommand (`my-cli hello -o json`).

### Entrypoint

```python
# src/my_cli/__init__.py
def main_entrypoint() -> None:
    app()

# pyproject.toml
# [project.scripts]
# my-cli = "my_cli:main_entrypoint"
```

---

## Testing

```bash
# Run directly during dev
uv run my-cli hello --output json

# Install locally and test as if deployed
uv tool install . --force
my-cli hello --output json

# Test from GitHub (after push)
uv tool install git+https://github.com/USER/REPO.git
```

---

*See @~/.claude/rules/agent-friendly-cli.md for AI agent consumption patterns (HATEOAS, exit codes, composability).*
