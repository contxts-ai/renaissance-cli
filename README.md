# Renaissance CLI (`ren`)

Portable CLI for controlling Renaissance platform services — Temporal pipelines, cron schedules, Claude Server execution, and agent management. Designed for both human operators and AI agents.

## Install

```bash
# Requires Python 3.12+ and uv
uv tool install git+https://github.com/Minsu-Daniel-Kim/renaissance-cli.git

# Upgrade to latest
uv tool upgrade renaissance-cli

# Uninstall
uv tool uninstall renaissance-cli
```

## Setup

### First-time authentication

```bash
# Local development (Trigger API on localhost)
ren auth login --key <API_KEY>

# Remote (production / other machines)
ren auth login \
  --trigger-url https://trigger.renaissance.financial \
  --claude-url https://claude-server.renaissance.financial \
  --key <API_KEY>

# Verify configuration
ren auth status

# Check connectivity
ren status
```

Credentials are saved to `~/.config/renaissance/cli.json`.

### Configuration precedence

```
Environment variables  >  Config file  >  Defaults
TRIGGER_URL               cli.json        http://localhost:58100
TRIGGER_API_KEY            cli.json        (none)
CLAUDE_SERVER_URL          cli.json        http://localhost:58000
```

---

## Commands

### `ren status`

Check overall system health (Trigger API, Temporal, Claude Server).

```bash
ren status
ren status -o json
```

---

### `ren pipeline` — Launch, monitor, and control pipelines

#### Launch pipelines

```bash
# From a template
ren pipeline launch --template research-pipeline --target wstETH
ren pipeline launch --template e2e-test --target sUSDe --no-pause

# Specialized launch modes
ren pipeline launch-research --target wstETH
ren pipeline launch-coding --target wstETH
ren pipeline launch-forge --skill token-deep-researcher
ren pipeline orchestrate --goal "Analyze cbBTC collateral risk" --target cbBTC
```

#### Monitor progress

```bash
# One-shot status check
ren pipeline progress <workflow_id>

# Live polling (updates every 3s until terminal state)
ren pipeline progress <workflow_id> --watch

# Custom poll interval
ren pipeline progress <workflow_id> --watch --interval 5
```

#### Control running pipelines

```bash
ren pipeline pause <workflow_id>
ren pipeline resume <workflow_id>
ren pipeline approve <workflow_id>      # Approve HITL gate
ren pipeline cancel <workflow_id>
ren pipeline skip <workflow_id> <step_id>
```

#### List pipelines

```bash
ren pipeline list                       # Running pipelines (default)
ren pipeline list --status Completed    # Completed pipelines
ren pipeline list --status All          # All pipelines
ren pipeline list --prefix contract     # Filter by ID prefix
ren pipeline list --limit 50            # Increase result limit
```

---

### `ren schedule` — Manage cron schedules

#### Create a schedule

```bash
ren schedule create \
  --template research-pipeline \
  --target wstETH \
  --cron "0 */6 * * *" \
  --note "Research wstETH every 6 hours"
```

#### List and inspect

```bash
ren schedule list
ren schedule list --query "ScheduleId STARTS_WITH 'sched-research'"
ren schedule show <schedule_id>
```

#### Control schedules

```bash
ren schedule pause <schedule_id>
ren schedule resume <schedule_id>
ren schedule trigger <schedule_id>                  # One-time immediate run
ren schedule update <schedule_id> --cron "0 0 * * *" --note "Daily"
ren schedule delete <schedule_id> --yes             # Skip confirmation
```

---

### `ren execute` — Run prompts on Claude Server

#### Execute a prompt

```bash
# Fire and forget (returns task_id)
ren execute prompt "Analyze the risk profile of wstETH"

# Wait for result
ren execute prompt "Say hello in one word" --wait

# With system prompt and model override
ren execute prompt "Explain DeFi lending" \
  --system "You are a DeFi analyst." \
  --model claude-sonnet-4-5-20250514 \
  --wait
```

#### Check task status

```bash
ren execute status <task_id>
ren execute status <task_id> --wait     # Poll until completion
```

---

### `ren template` — Discover pipeline templates

```bash
# List all templates with descriptions
ren template list

# Show template details (steps, dependencies, configuration)
ren template show research-pipeline
```

---

### `ren metrics` — Execution analytics

```bash
# Summary by template (default: last 7 days)
ren metrics summary
ren metrics summary --days 30

# Step-level skill invocation metrics
ren metrics steps
ren metrics steps --days 14 --limit 50
```

---

### `ren agent` — Manage registered agents

```bash
ren agent list                          # List all agents
ren agent run <agent_name> --target X   # Run an agent
ren agent status <workflow_id>          # Check agent progress
```

---

### `ren auth` — Credential management

```bash
ren auth login --trigger-url <URL> --claude-url <URL> --key <KEY>
ren auth status                         # Show current config and sources
ren auth logout                         # Remove saved credentials
```

---

## Output Formats

All commands support `--output` (`-o`) with three formats:

| Format | Flag | Use case |
|--------|------|----------|
| `text` | `-o text` | Human-readable (default in terminal) |
| `json` | `-o json` | Structured output for agents and scripts |
| `jsonl` | `-o jsonl` | Newline-delimited JSON for streaming/piping |

When stdout is piped (not a TTY), output automatically switches to JSON.

### Response envelope

Every JSON response follows this structure:

```json
{
  "ok": true,
  "result": { "..." },
  "next_actions": [
    {"command": "ren pipeline progress abc-123", "description": "Watch progress"}
  ]
}
```

Error responses include a `fix` hint:

```json
{
  "ok": false,
  "error": {
    "code": "AUTH_ERROR",
    "message": "Authentication failed",
    "fix": "Run: ren auth login --trigger-url <URL> --key <KEY>"
  }
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Usage error (bad arguments) |
| 3 | Authentication failure |
| 4 | Resource not found |
| 5 | Conflict |
| 6 | Timeout |
| 7 | Connection error |

---

## For AI Agents

This CLI is designed for AI agent consumption. Agents discover commands through three layers:

1. **`--help`** — progressive command/parameter discovery (~200 tokens)
2. **`-o json`** — structured responses, no parsing needed
3. **`next_actions`** — HATEOAS-style hints for what to do next

### Example agent workflow

```bash
# 1. Agent discovers available templates
ren template list -o json

# 2. Launches a pipeline
ren pipeline launch --template research-pipeline --target wstETH -o json
# → response includes: next_actions: [{"command": "ren pipeline progress <wf_id>"}]

# 3. Agent follows next_actions to monitor
ren pipeline progress <wf_id> -o json

# 4. If paused, agent approves
ren pipeline approve <wf_id> -o json
```

### Environment variable overrides

```bash
export REN_OUTPUT=json          # Default all commands to JSON
export TRIGGER_URL=https://...  # Override Trigger API URL
export TRIGGER_API_KEY=...      # Override API key
export CLAUDE_SERVER_URL=...    # Override Claude Server URL
```

---

## Architecture

```
ren (CLI)  ──HTTP──▶  Trigger API (:58100)  ──▶  Temporal Cloud
           ──HTTP──▶  Claude Server (:58000) ──▶  Claude Agent SDK
```

The CLI is a thin HTTP client — it does not require local access to any repository or service code. Any machine with network access to the APIs can use it.

---

## Development

```bash
# Clone and develop
git clone git@github.com:Minsu-Daniel-Kim/renaissance-cli.git
cd renaissance-cli
uv sync
uv run ren --help

# Install locally for testing
uv tool install . --force

# Run tests
uv run ren status -o json
```

## Design Guides

- [Agent-Friendly CLI Design](docs/agent-friendly-cli.md) — HATEOAS, output contracts, composability
- [CLI Development Guide](docs/cli-dev-guide.md) — Typer patterns, uv distribution
