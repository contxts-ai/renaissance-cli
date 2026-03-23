# Renaissance CLI (`ren`)

Portable CLI for controlling Renaissance platform services — Temporal pipelines, cron schedules, Claude Server execution, agent management, and ambient agents. Designed for both human operators and AI agents.

## Install

```bash
# Requires Python 3.12+ and uv
uv tool install git+https://github.com/contxts-ai/renaissance-cli.git

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

# Ralph Loop (see also: ren ralph)
ren pipeline launch-ralph -t wstETH --describe "Add two numbers" --name add_numbers
```

#### Monitor progress

```bash
ren pipeline progress <workflow_id>
ren pipeline progress <workflow_id> --watch
ren pipeline progress <workflow_id> --watch --interval 5
```

#### Control running pipelines

```bash
ren pipeline pause <workflow_id>
ren pipeline resume <workflow_id>
ren pipeline approve <workflow_id>          # Approve HITL gate
ren pipeline cancel <workflow_id>
ren pipeline terminate <workflow_id> -y     # Force-terminate
ren pipeline skip <workflow_id> <step_id>
ren pipeline auto <workflow_id> <step_id>   # Toggle auto-execution
ren pipeline start-phase2 <workflow_id>     # Research: start phase 2
```

#### Inspect pipeline internals

```bash
ren pipeline dag <workflow_id>                          # DAG structure
ren pipeline step-output <workflow_id> <step_id>        # Step output
ren pipeline step-ops <workflow_id> <step_id>           # Artifact/KG ops
ren pipeline function <workflow_id> <function_id>       # Generated code
ren pipeline lineage <workflow_id>                      # Chain lineage
```

#### Backfill pipelines

```bash
ren pipeline launch-backfill --target T --metric-id M \
  --collector-module cm --collector-function cf \
  --start-block 1000 --end-block 2000
ren pipeline backfill-progress <workflow_id> --watch

ren pipeline launch-backfill-build --target T --steps-file steps.json
ren pipeline backfill-build-progress <workflow_id> --watch
```

#### Batch operations

```bash
ren pipeline batch --template research-pipeline --targets wstETH,cbBTC,sUSDe
ren pipeline batch-resume <wf1>,<wf2>,<wf3>
ren pipeline batch-cancel <wf1>,<wf2>,<wf3> -y
```

#### Replay

```bash
ren pipeline replay <workflow_id> -y
ren pipeline replay-from <workflow_id> <step_id> -y
```

#### List pipelines

```bash
ren pipeline list                       # Running pipelines (default)
ren pipeline list --status Completed
ren pipeline list --status All
ren pipeline list --prefix contract --limit 50
```

---

### `ren ralph` — Ralph Loop convergence pipelines

```bash
# Launch
ren ralph launch -t test --describe "Add two numbers" --name add_numbers
ren ralph launch -t myproject --spec ./my_spec.json
ren ralph launch -t wstETH                          # coding-planner mode

# Monitor
ren ralph progress <workflow_id>
ren ralph progress <workflow_id> --watch

# Inspect per-function convergence
ren ralph function <workflow_id> <function_id>
ren ralph function <workflow_id> <function_id> --watch

# Browse workspace files
ren ralph workspace <workflow_id> --function <fid>
ren ralph file <workflow_id> --function <fid> --path src/main.py

# Show FunctionSpec schema and examples
ren ralph spec
```

---

### `ren schedule` — Manage cron schedules

```bash
# Create
ren schedule create --template research-pipeline --target wstETH \
  --cron "0 */6 * * *" --note "Research every 6 hours"

# List and inspect
ren schedule list
ren schedule show <schedule_id>

# Control
ren schedule pause <schedule_id>
ren schedule resume <schedule_id>
ren schedule trigger <schedule_id>              # One-time run
ren schedule update <schedule_id> --cron "0 0 * * *"
ren schedule delete <schedule_id> --yes
```

---

### `ren execute` — Run prompts on Claude Server

```bash
# Execute a prompt
ren execute prompt "Analyze wstETH risk" --wait
ren execute prompt "Hello" --system "You are a DeFi analyst." --model claude-sonnet-4-5-20250514

# Check status
ren execute status <task_id>
ren execute status <task_id> --wait

# List and cancel tasks
ren execute list
ren execute list --status running
ren execute cancel <task_id> -y
```

---

### `ren eval` — Online skill evaluations

```bash
# Trigger an eval
ren eval trigger --skill token-deep-researcher
ren eval trigger --skill my-skill --request "test input" --mode agent

# View results
ren eval detail <eval_id>
ren eval result <workflow_id>
```

---

### `ren ambient` — Ambient decision agents

```bash
# List active ambient schedules
ren ambient list

# Check mission decision history
ren ambient status <mission_id>

# Manually trigger a decision
ren ambient wake <mission_id> --reason "Manual check"

# Manage schedules (5-min recurring)
ren ambient schedule <mission_id>
ren ambient unschedule <mission_id> -y

# View default policy
ren ambient policy
```

---

### `ren agent` — Registered agents

```bash
ren agent list                          # List all agents
ren agent list --standalone             # Standalone agents only
ren agent run <name> --target X         # Run an agent
ren agent run <name> -t X --watch       # Run and wait
ren agent status <workflow_id>          # Check progress
```

---

### `ren template` — Pipeline templates

```bash
ren template list
ren template show research-pipeline
```

---

### `ren metrics` — Execution analytics

```bash
ren metrics summary                     # Last 7 days by template
ren metrics summary --days 30
ren metrics steps --days 14 --limit 50  # Skill-level stats
```

---

### `ren auth` — Credential management

```bash
ren auth login --trigger-url <URL> --claude-url <URL> --key <KEY>
ren auth status
ren auth logout
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
# 1. Discover templates
ren template list -o json

# 2. Launch a pipeline
ren pipeline launch --template research-pipeline --target wstETH -o json

# 3. Follow next_actions to monitor
ren pipeline progress <wf_id> -o json

# 4. Inspect DAG structure
ren pipeline dag <wf_id> -o json

# 5. If paused, approve
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
git clone git@github.com:contxts-ai/renaissance-cli.git
cd renaissance-cli
uv sync
uv run ren --help

# Install locally for testing
uv tool install . --force
```

## Design Guides

- [Agent-Friendly CLI Design](docs/agent-friendly-cli.md) — HATEOAS, output contracts, composability
- [CLI Development Guide](docs/cli-dev-guide.md) — Typer patterns, uv distribution
