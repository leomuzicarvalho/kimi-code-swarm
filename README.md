# Kimi Swarm CLI

A swarm orchestration CLI and framework for **Kimi Code** that enables multi-agent collaboration with real-time status visibility.

## Features

- **Agent Orchestration**: Spawn, manage, and coordinate multiple specialized agents
- **Real-time Status**: View agent phases, progress, and token usage directly in Kimi's window
- **Context Window Tracking**: Compare each agent's context window against the main agent
- **Ruflo Integration**: Built-in bridge to Ruflo MCP for native swarm execution
- **Multiple Topologies**: Hierarchical, mesh, and consensus swarm layouts

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Initialize a swarm
kimi-swarm init --topology hierarchical --max-agents 5

# Spawn agents
kimi-swarm spawn --type coder --name feature-dev --model sonnet
kimi-swarm spawn --type tester --name qa-bot --model haiku

# Check status (formatted for Kimi's window)
kimi-swarm status --kimi-display

# Execute a task
kimi-swarm execute --agent feature-dev --task "Implement login feature"

# Shutdown
kimi-swarm shutdown
```

## Python API

```python
from kimi_swarm import SwarmOrchestrator, AgentConfig

orch = SwarmOrchestrator(topology="hierarchical", max_agents=5)
orch.spawn_agent(AgentConfig(type="coder", name="dev-1", model="sonnet"))
status = orch.get_status()
print(status.to_kimi_markdown())
```
