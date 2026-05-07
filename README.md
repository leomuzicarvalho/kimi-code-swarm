# 🐝 Kimi Swarm CLI

A swarm orchestration CLI and framework for **Kimi Code** that enables multi-agent collaboration with real-time status visibility directly in Kimi's chat window.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-21%20passing-green.svg)]()

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
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
   │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  ...
   │ (coder) │  │ (tester)│  │(reviewer│
   └────┬────┘  └────┬────┘  └────┬────┘
        │            │            │
        └────────────┴────────────┘
                     │
            ┌────────▼────────┐
            │  Ruflo MCP      │
            │    Bridge       │
            └─────────────────┘
```

1. **Initialize** a swarm with a topology (`hierarchical`, `mesh`, or `consensus`)
2. **Spawn agents** with roles, models, and specializations
3. **Assign & execute tasks** — the orchestrator routes work via the Ruflo-Kimi Bridge
4. **Monitor** all agents in real-time with `kimi-swarm status --kimi-display`
5. **Store memory** and retrieve results when agents complete

### Model Mapping (Ruflo → Kimi)

When you spawn an agent with a Ruflo model alias, it resolves to the actual Kimi model:

| Ruflo Alias | Resolved Kimi Model | Context Window |
|-------------|---------------------|----------------|
| `sonnet` | `kimi-k2.6` | **256,000 tokens** |
| `opus` | `kimi-k2.6` | **256,000 tokens** |
| `inherit` | `kimi-k2.6` | **256,000 tokens** |
| `haiku` | `moonshot-v1-8k` | 8,192 tokens |

You can also pass **explicit Kimi model names** directly:
- `moonshot-v1-8k`, `moonshot-v1-32k`, `moonshot-v1-128k`
- `kimi-k2-0712-preview` (128k)
- `kimi-k2.6` (256k)

### Execution Modes

The Ruflo-Kimi Bridge auto-selects the execution backend:

1. **Anthropic API** — if `ANTHROPIC_API_KEY` is set
2. **Kimi API** — if `KIMI_API_KEY` or `MOONSHOT_API_KEY` is set
3. **Native Kimi** — no API key; returns delegation prompts that Kimi Code executes directly with its own tools

---

## Installation on Kimi Code

### Option A: Install in the Same Environment as Kimi Code

If you have terminal access to the machine running Kimi Code:

```bash
git clone git@github.com:leomuzicarvalho/kimi-code-swarm.git
cd kimi-code-swarm
pip install -e ".[dev]"
```

This makes `kimi-swarm` available as a CLI command globally.

### Option B: Use as a Python Module Within Kimi Code

Since Kimi Code can run Python inline, you can also import the framework directly in a Kimi session:

```python
# In Kimi Code's terminal or a Python cell
import sys
sys.path.insert(0, "/path/to/kimi-code-swarm")

from kimi_swarm import SwarmOrchestrator, AgentConfig, KimiDisplay

orch = SwarmOrchestrator(topology="hierarchical", max_agents=5)
orch.init_swarm()
```

### Option C: pip install from GitHub

```bash
pip install git+ssh://git@github.com/leomuzicarvalho/kimi-code-swarm.git
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

# 4. Execute tasks
kimi-swarm execute --agent fe --task "Build a login page with OAuth"
kimi-swarm execute --agent be --task "Create JWT auth middleware"

# 5. Check progress again
kimi-swarm status --kimi-display

# 6. Shutdown
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

| Agent | Type | Requested → Kimi Model | Phase | Progress | Context (Agent) | Context (vs Main) | Tokens |
|-------|------|------------------------|-------|----------|-----------------|-------------------|--------|
| 🆕 **arch** | architect | `sonnet` → `kimi-k2.6` | `idle` | ░░░░░░░░░░ 0% | 0 / 256,000 (0.0%) | 0.0x | 0 (↗0) |
| ✅ **fe** | coder | `sonnet` → `kimi-k2.6` | `completed` | ██████████ 100% | 3,200 / 256,000 (1.3%) | 0.3x | 3,200 (↗1,100) |
| ⚡ **be** | coder | `haiku` → `moonshot-v1-8k` | `executing` | ██████░░░░ 60% | 5,800 / 8,192 (70.8%) | 0.5x | 5,800 (↗2,400) |
| 👀 **sec** | reviewer | `sonnet` → `kimi-k2.6` | `reviewing` | ███████░░░ 75% | 2,100 / 256,000 (0.8%) | 0.2x | 2,100 (↗800) |

---
**Legend:**
- 🆕 idle | ⏳ planning | ⚡ executing | 👀 reviewing | ⏸️ waiting | ✅ completed | ❌ failed | 🛑 terminated
```

### Columns Explained

| Column | Meaning |
|--------|---------|
| **Agent** | Name + phase emoji |
| **Type** | Role (coder, tester, reviewer, etc.) |
| **Requested → Kimi Model** | The alias you passed and the actual Kimi model it resolves to |
| **Phase** | Current lifecycle state |
| **Progress** | Visual bar + percentage for the agent's active task |
| **Context (Agent)** | Used / Max tokens + percent for this agent's context window |
| **Context (vs Main)** | Ratio of agent's used tokens to main agent's used tokens |
| **Tokens** | Total tokens consumed (with completion tokens in ↗) |

---

## All CLI Commands

| Command | Description |
|---------|-------------|
| `kimi-swarm init` | Create a new swarm |
| `kimi-swarm spawn` | Add an agent |
| `kimi-swarm status` | Show swarm status (`--kimi-display` for markdown, `--json` for JSON) |
| `kimi-swarm assign` | Give an agent a task without executing |
| `kimi-swarm execute` | Run a task on an agent |
| `kimi-swarm progress` | Manually update an agent's progress % |
| `kimi-swarm phase` | Manually set an agent's phase |
| `kimi-swarm terminate` | Kill an agent |
| `kimi-swarm shutdown` | Tear down the entire swarm |
| `kimi-swarm demo` | Run a full demo with sample agents and tasks |

---

## Development

```bash
# Run tests
pytest tests/test_swarm.py -v

# Run the demo
python demo.py
```

---

## Requirements

- Python 3.10+
- `rich` (for terminal formatting)
- `pydantic` (for data validation)
- Optional: Ruflo-Kimi Bridge MCP server (for real multi-agent execution)

Without the MCP bridge, the framework runs in **mock mode** — it simulates agent execution so you can build and test workflows locally before connecting to live agents.

---

## License

MIT
