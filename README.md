# 🐝 Kimi Swarm CLI

A swarm orchestration CLI and framework for **Kimi Code** that enables multi-agent collaboration with real-time status visibility directly in Kimi's chat window.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-35%20passing-green.svg)]()

---

## What It Does

Kimi Swarm lets you spin up a **team of specialized AI agents** (coders, testers, reviewers, architects, security auditors) that work in parallel on different parts of a task. You can monitor every agent's:

- **Name & Role** — who is doing what
- **Phase** — idle, planning, executing, reviewing, completed, failed
- **Progress** — visual progress bar with percentage
- **Context Window** — tokens used vs. max for each agent
- **Context vs. Main Agent** — how an agent's context compares to the orchestrator's
- **Token Usage** — prompt + completion breakdown

All of this renders as a **markdown table directly in Kimi's chat window** so you can see the entire swarm state at a glance.

🌐 **New: Live Web Dashboard** — Add `--ui` to any command (or run `kimi-swarm ui`) to open a beautiful, real-time browser dashboard with animated agent cards, token gauges, and an overall progress ring. The dashboard auto-updates via Server-Sent Events and persists across CLI commands.

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────┐
│           Kimi Code (Main Agent)            │
│         ┌─────────────────────┐             │
│         │  SwarmOrchestrator  │             │
│         └──────────┬──────────┘             │
└────────────────────┼────────────────────────┘
                     │
            ┌────────┼────────┐
            │        │        │
       ┌────▼────┐ ┌──▼───┐ ┌──▼───┐
       │ Agent 1 │ │Agent2│ │Agent3│  ...
       │ (coder) │ │(tester)│(reviewer│
       └─────────┘ └──────┘ └──────┘
```

1. **Initialize** a swarm with a topology (`hierarchical`, `mesh`, or `consensus`)
2. **Spawn agents** with roles, models, and specializations
3. **Assign & execute tasks** — the orchestrator routes work to agents
4. **Monitor** all agents in real-time with `kimi-swarm status --kimi-display`
5. **Store memory** and retrieve results when agents complete

### Model Mapping

When you spawn an agent with a model alias, it resolves to the actual Kimi model:

| Alias | Resolved Kimi Model | Context Window |
|-------|---------------------|----------------|
| `sonnet` | `kimi-k2.6` | **256,000 tokens** |
| `opus` | `kimi-k2.6` | **256,000 tokens** |
| `inherit` | `kimi-k2.6` | **256,000 tokens** |
| `haiku` | `moonshot-v1-8k` | 8,192 tokens |

You can also pass **explicit Kimi model names** directly:
- `moonshot-v1-8k`, `moonshot-v1-32k`, `moonshot-v1-128k`
- `kimi-k2-0712-preview` (128k)
- `kimi-k2.6` (256k)

---

## MCP Server Setup

To use Kimi Swarm **inside Kimi Code chat** (as MCP tools rather than terminal commands), add this to `~/.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "kimi-swarm": {
      "command": "/absolute/path/to/your/python3",
      "args": ["-m", "kimi_swarm.mcp_server"],
      "autoStart": true
    }
  }
}
```

> ⚠️ **Important:** Use the **absolute path** to the Python interpreter that has `kimi-swarm` installed. If you use `"command": "python3"`, running `kimi` from a project with an active virtual environment will cause the MCP server to spawn with the venv's Python — which won't have `kimi-swarm` installed and the connection will fail.

If you're using the local `.venv` from this repo, point to it directly:
```json
{
  "mcpServers": {
    "kimi-swarm": {
      "command": "/Users/leonardomuzi/kimi-swarm-cli/.venv/bin/python",
      "args": ["-m", "kimi_swarm.mcp_server"],
      "autoStart": true
    }
  }
}
```

### Apple Silicon Macs (M1/M2/M3/M4)

On Apple Silicon with a **universal Python binary** (e.g., from python.org), the MCP server may fail with:

```
ImportError: dlopen(...): mach-o file, but is an incompatible architecture
```

This happens when Python packages with native extensions (like `pydantic-core`) are installed for one architecture (e.g., x86_64 under Rosetta) but the MCP server runs as another (arm64). To force the MCP server to always run as **arm64** (matching Apple Silicon hardware), wrap the command with `arch`:

```json
{
  "mcpServers": {
    "kimi-swarm": {
      "command": "arch",
      "args": ["-arm64", "/absolute/path/to/your/python3", "-m", "kimi_swarm.mcp_server"],
      "autoStart": true
    }
  }
}
```

The [install.sh](#one-liner-install-recommended) script automatically detects this situation and writes the `arch -arm64` wrapper for you.

---

## Installation on Kimi Code

### One-liner Install (Recommended)

Run this **inside the terminal of your Kimi Code instance** (or any shell that shares the same Python environment):

```bash
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash
```

This detects your Python, installs `kimi-swarm` into the **current environment only**, and verifies the CLI is available immediately. No sudo, no system-wide changes.

> 🍎 **Apple Silicon Macs:** The installer automatically detects universal Python binaries (e.g., from python.org) and forces ARM64 architecture during pip installs, preventing the common `mach-o file, but is an incompatible architecture (have 'x86_64', need 'arm64')` error. It also scans for x86_64-only native extensions after installation and auto-fixes them.

#### Install Options

```bash
# Install into current environment (default)
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash

# Install into a dedicated virtualenv (isolated)
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash -s -- --venv ~/.venvs/kimi-swarm

# Install from a specific branch
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash -s -- --branch dev

# Install for current user only (no root)
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash -s -- --user
```

### Manual Install (if you prefer)

**Recommended: use a local venv** to avoid polluting your system Python and to prevent architecture cache issues on Apple Silicon:

```bash
git clone git@github.com:leomuzicarvalho/kimi-code-swarm.git
cd kimi-code-swarm
python3 -m venv .venv

# On Apple Silicon Macs, force ARM64 to avoid x86_64 wheel cache issues
arch -arm64 .venv/bin/pip install --no-cache-dir -e ".[dev]"

# On other platforms
.venv/bin/pip install -e ".[dev]"
```

Then activate it in any terminal session:
```bash
source .venv/bin/activate
```

Or run commands directly via the venv:
```bash
.venv/bin/kimi-swarm --version
.venv/bin/python -m kimi_swarm.mcp_server
```

### Use as a Python Module Within Kimi Code

If you don't want the CLI and just want to import the framework directly in a Kimi session:

```python
# In Kimi Code's terminal or a Python cell
import sys
sys.path.insert(0, "/path/to/kimi-code-swarm")

from kimi_swarm import SwarmOrchestrator, AgentConfig, KimiDisplay

orch = SwarmOrchestrator(topology="hierarchical", max_agents=5)
orch.init_swarm()
```

---

## Uninstall

To completely remove Kimi Swarm and all its integrations:

```bash
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/uninstall.sh | bash
```

This removes the Python package, MCP server registration, skill file, and startup hook.

| Option | Effect |
|--------|--------|
| `--yes` | Skip confirmation and uninstall immediately |
| `--purge` | Also remove swarm state file and `mcp.json` backups |

```bash
# Interactive uninstall (shows summary, asks for confirmation)
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/uninstall.sh | bash

# Uninstall without prompts
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/uninstall.sh | bash -s -- --yes

# Full cleanup including state and backups
curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/uninstall.sh | bash -s -- --yes --purge
```

---

## Quick Start

### CLI Usage

```bash
# 1. Initialize a swarm
kimi-swarm init --topology hierarchical --max-agents 5

# 2. Spawn specialized agents
kimi-swarm spawn --type architect --name arch --model sonnet
kimi-swarm spawn --type coder     --name fe    --model sonnet
kimi-swarm spawn --type coder     --name be    --model haiku
kimi-swarm spawn --type tester    --name qa    --model haiku
kimi-swarm spawn --type reviewer  --name sec   --model sonnet

# 3. View status in Kimi's window (markdown table)
kimi-swarm status --kimi-display

# 4. Open the live web dashboard
kimi-swarm ui

# 5. Execute tasks (with dashboard auto-opening)
kimi-swarm execute --agent fe --task "Build a login page with OAuth" --ui
kimi-swarm execute --agent be --task "Create JWT auth middleware" --ui

# 6. Check progress again
kimi-swarm status --kimi-display

# 7. Shutdown
kimi-swarm shutdown
```

### Python API Usage (Inside Kimi Code)

```python
from kimi_swarm import SwarmOrchestrator, AgentConfig, KimiDisplay

# Initialize
orch = SwarmOrchestrator(topology="hierarchical", max_agents=5)
orch.init_swarm()

# Spawn agents
orch.spawn_agent(AgentConfig(type="coder", name="frontend", model="sonnet"))
orch.spawn_agent(AgentConfig(type="coder", name="backend", model="haiku"))

# Execute work
orch.execute_task("<agent-id>", "Implement feature X")

# Get status formatted for Kimi's window
status = orch.get_status()
print(KimiDisplay.status_to_markdown(status))
```

---

## What You See in Kimi's Window

Running `kimi-swarm status --kimi-display` outputs a markdown table that renders beautifully in Kimi's chat:

```markdown
## 🐝 Swarm Status

**Swarm ID:** `swarm-abc123`  |  **Topology:** `hierarchical`  |  **Active:** 4/5

📊 **Overall Progress:** 75.0%  |  **Tasks:** 3/4 completed

### 🧠 Main Agent Context
- **Used:** 12,450 / 128,000 tokens (9.7%)
- **Available:** 115,550 tokens

### 🤖 Agents

| Agent | Type | Model | Phase | Progress | Context | Prompt / Comp | Msg | Uptime | Task |
|-------|------|-------|-------|----------|---------|-------------|-----|--------|------|
| 🆕 **arch** | architect | `sonnet` → `kimi-k2.6` | `idle` | ░░░░░░░░░░ 0% | 0 / 256,000 (0.0%) | 0 / 0 | 0 | 0s | |
| ✅ **fe** | coder | `sonnet` → `kimi-k2.6` | `completed` | ██████████ 100% | 3,200 / 256,000 (1.3%) | 2,100 / 1,100 | 12 | 5m 3s | Build login page with OAuth |
| ⚡ **be** | coder | `haiku` → `moonshot-v1-8k` | `executing` | ██████░░░░ 60% | 5,800 / 8,192 (70.8%) | 3,400 / 2,400 | 8 | 2m 15s | Create JWT auth middleware |
| 👀 **sec** | reviewer | `sonnet` → `kimi-k2.6` | `reviewing` | ███████░░░ 75% | 2,100 / 256,000 (0.8%) | 1,300 / 800 | 5 | 4m 30s | Review auth implementation |

---
**Legend:**
- 🆕 idle | ⏳ planning | ⚡ executing | 👀 reviewing | ⏸️ waiting | ✅ completed | ❌ failed | 🛑 terminated
```

### Columns Explained

| Column | Meaning |
|--------|---------|
| **Agent** | Name + phase emoji |
| **Type** | Role (coder, tester, reviewer, etc.) |
| **Model** | The alias you passed and the actual Kimi model it resolves to |
| **Phase** | Current lifecycle state |
| **Progress** | Visual bar + percentage for the agent's active task |
| **Context** | Used / Max tokens + percent for this agent's context window |
| **Prompt / Comp** | Prompt tokens vs completion tokens consumed |
| **Msg** | Number of messages exchanged with the agent |
| **Uptime** | How long the agent has been alive (`Xs`, `Xm Xs`, `Xh Xm`) |
| **Task** | Current task description (truncated to 30 chars) |

---

## Live Web Dashboard

The web dashboard opens in your default browser and stays live as long as the swarm is active. It features:

- 🎨 **Dark glassmorphism UI** with animated particle network background
- 📊 **Circular progress ring** showing overall swarm completion
- 🤖 **Live agent cards** with phase colors, pulse animations, and smooth progress bars
- 📈 **Token usage visualization** — Prompt, Completion, Total, Context Used/Max, and Messages count
- ⏱️ **Agent lifetime tracking** — Uptime, Spawned time, and Last Active (with smart relative formatting)
- 📝 **Task visibility** — Task description and Task Status (`pending` / `in_progress` / `completed` / `failed`)
- 🟢 **Connection status** indicator with auto-reconnect
- 🔴 **Offline overlay** when no swarm is detected

```bash
# Open dashboard for existing swarm
kimi-swarm ui

# Auto-open dashboard on any command
kimi-swarm init --ui
kimi-swarm spawn --type coder --name fe --ui
kimi-swarm execute --agent fe --task "Build auth" --ui

# Custom port
kimi-swarm init --ui --port 8080
```

The dashboard runs as a **persistent background process** — it survives individual CLI commands and only stops when you run `kimi-swarm shutdown`.

---

## Sticky Live Status via Todo Sync

When using the **MCP server** inside Kimi Code, every swarm tool response includes a `todos` array. The AI syncs this to `SetTodoList` after each operation, giving you a live-updating status panel:

- **Web UI** — appears in the prompt toolbar as an expandable todo panel
- **Shell UI** — renders as display blocks in the conversation

Each agent maps to a todo item with its phase and a visual progress bar (`██████████ 100%`). As agents move from `idle` → `executing` → `completed`, the todo list updates automatically.

---

## Agentic Loop with Verification (MCP Only)

When using the MCP server inside Kimi Code, you can run tasks through a **verification loop** that automatically retries on failure:

```
┌─────────────┐    execute+verify    ┌──────────┐
│  dev-loop   │ ───────────────────► │ verifier │
└─────────────┘                      └────┬─────┘
       ▲                                  │
       │              FAILED              │
       └──────────────────────────────────┘
       │                                  │
       ▼                                  ▼
┌─────────────┐    acknowledge_failure   │
│ coordinator │ ◄────────────────────────┘
│(entry-point)│
└──────┬──────┘
       │ reassign_with_feedback
       ▼
┌─────────────┐
│  dev-loop   │ (next iteration with feedback)
│  (retry)    │
└─────────────┘
```

**MCP Tools:**

| Tool | Purpose |
|------|---------|
| `agent_execute_with_verification` | Execute a task with verifier check. If it fails, returns `needs_retry: true` and `route_to_entry_point`. After every iteration the dashboard is updated. |
| `agent_acknowledge_failure` | Entry-point agent digests the failure history (attempt count, feedback) and prepares for reassignment. |
| `agent_reassign_with_feedback` | Route the corrected task to another agent, carrying forward all iteration history and verification feedback. |
| `swarm_verify_dashboard` | Check that the dashboard is responding, state is fresh (< 5s), and agent counts match. |

The loop respects `max_iterations` (default 3). On the final failure, `needs_retry` becomes `false` and manual review is required.

## Browser Tab Deduplication

The swarm guarantees **only one browser tab** is ever opened:

- A 30-second cooldown lock file (`~/.kimi/kimi-swarm-browser.lock`) prevents duplicate tabs
- `swarm_init` stops any existing dashboard before starting fresh
- `swarm_ui` reuses an existing persistent dashboard instead of spawning duplicates
- `kimi-swarm shutdown` clears the lock so the next init can open a new tab

| Scenario | Result |
|----------|--------|
| `swarm_init` → `swarm_init` again | 1 tab, fresh dashboard |
| `swarm_init` → `swarm_ui` | 1 tab (reuses persistent dashboard) |
| Multiple `swarm_ui` calls | 1 tab (30s cooldown) |
| `shutdown` → `init` | Clean stop + fresh start with new tab |

## All CLI Commands

| Command | Description |
|---------|-------------|
| `kimi-swarm init` | Create a new swarm (`--ui` to open dashboard) |
| `kimi-swarm spawn` | Add an agent (`--ui` to open dashboard) |
| `kimi-swarm status` | Show swarm status (`--kimi-display` for markdown, `--json` for JSON) |
| `kimi-swarm assign` | Give an agent a task without executing |
| `kimi-swarm execute` | Run a task on an agent (`--ui` to open dashboard) |
| `kimi-swarm progress` | Manually update an agent's progress % |
| `kimi-swarm phase` | Manually set an agent's phase |
| `kimi-swarm terminate` | Kill an agent |
| `kimi-swarm shutdown` | Tear down the entire swarm (stops dashboard) |
| `kimi-swarm ui` | Open the live web dashboard for the current swarm |
| `kimi-swarm demo` | Run a full demo with sample agents and tasks |

---

## Development

```bash
# Run tests
pytest tests/test_swarm.py -v

# Run only non-MCP tests
pytest tests/test_swarm.py -v -k "not MCP"

# Run the demo
python demo.py
```

---

## Requirements

- Python 3.10+
- `rich` (for terminal formatting)
- `pydantic` (for data validation)

The framework runs in **local simulation mode** — it simulates agent execution so you can build and test workflows. For real multi-agent execution, tasks are delegated back to Kimi Code directly.

---

## License

MIT
