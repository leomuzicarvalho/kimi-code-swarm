---
name: kimi-swarm
description: Orchestrate multi-agent swarms using the kimi-swarm MCP server. Spawn agents, manage tasks, track progress, and monitor context windows across agents. Use when the user asks about swarms, agents, distributed tasks, parallel coding, or wants to view swarm status.
---

# Kimi Swarm Orchestration

Coordinate intelligent multi-agent swarms via the `kimi-swarm` MCP server.

## Startup Status

To see swarm status automatically when starting a session, add a `SessionStart` hook in `~/.kimi/config.toml`:

```toml
[[hooks]]
event = "SessionStart"
matcher = "startup|resume"
command = """python3 -c "import json,sys,os,subprocess; p=os.path.expanduser('~/.kimi/kimi-swarm-state.json'); os.path.exists(p) and (print('\n🐝 Active swarm detected'), subprocess.run(['kimi-swarm','status','--kimi-display']))" """
```

If you see swarm status at startup, the swarm is already active and ready for commands.

## Sticky Live Status (Todo List Sync)

**Every swarm tool response now includes a `todos` array.** After **every** swarm operation (`swarm_init`, `agent_spawn`, `agent_execute`, `agent_assign`, `agent_progress`, `agent_phase`, `agent_terminate`, `swarm_shutdown`), call `SetTodoList` with the `todos` from the response. This keeps an up-to-date swarm status pinned in Kimi's toolbar (web UI) and as a display block in the conversation (shell UI).

Example workflow:
```
swarm_init(topology="hierarchical", max_agents=5)
→ response contains todos → SetTodoList(todos=response.todos)

agent_spawn(agent_type="coder", name="fe-dev", model="sonnet")
→ response contains todos → SetTodoList(todos=response.todos)
```

The todo list shows:
- Swarm header with agent count and overall progress
- Each agent as a todo item with phase and progress bar
- Auto-updating status as agents move through phases

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `swarm_init` | Create a new swarm (hierarchical/mesh/consensus) |
| `swarm_status` | Get full status with markdown + todo-sync data |
| `swarm_shutdown` | Shutdown swarm, optionally clear state |
| `agent_spawn` | Spawn an agent with type, name, model |
| `agent_execute` | Run a task on an agent |
| `agent_assign` | Assign a task without executing |
| `agent_progress` | Update agent progress 0-100 |
| `agent_phase` | Set agent phase (idle/planning/executing/etc) |
| `agent_terminate` | Terminate an agent |
| `agent_list` | List all agents |
| `swarm_demo` | Run a quick demo swarm |

## Model Mapping

| Alias | Resolved Kimi Model | Context |
|-------|---------------------|---------|
| `haiku` | `moonshot-v1-8k` | 8,192 |
| `sonnet` | `kimi-k2.6` | 256,000 |
| `opus` | `kimi-k2-0712-preview` | 128,000 |
| `inherit` | `kimi-k2.6` | 256,000 |

## Core Workflow

1. **Initialize**: `swarm_init` with topology and max_agents
2. **Sync todos**: `SetTodoList(todos=response.todos)` ← always do this
3. **Spawn agents**: `agent_spawn` for each role
4. **Sync todos**: `SetTodoList(todos=response.todos)` ← always do this
5. **Execute**: `agent_execute` or `agent_assign` + `agent_progress`
6. **Sync todos**: `SetTodoList(todos=response.todos)` ← always do this
7. **Monitor**: `swarm_status` anytime; sync todos to refresh sticky display
8. **Cleanup**: `swarm_shutdown` when done

## Quick Patterns

**Parallel coding swarm:**
```
swarm_init(topology="hierarchical", max_agents=5)
SetTodoList(todos=response.todos)
agent_spawn(agent_type="architect", name="arch-1", model="sonnet")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="coder", name="fe-dev", model="sonnet")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="coder", name="be-dev", model="haiku")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="tester", name="qa-1", model="haiku")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="reviewer", name="sec-1", model="sonnet")
SetTodoList(todos=response.todos)
agent_execute(agent_id="fe-dev-id", prompt="Build login page")
SetTodoList(todos=response.todos)
agent_execute(agent_id="be-dev-id", prompt="Implement auth API")
SetTodoList(todos=response.todos)
```

## Display

Always render the `markdown` field from `swarm_status` or `swarm_init` directly — it contains a formatted table with progress bars, context usage, and phase emojis. Additionally, always sync the `todos` array to `SetTodoList` so the swarm status stays sticky and live-updating in the conversation window.
