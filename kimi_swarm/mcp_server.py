"""MCP server for kimi-swarm — exposes swarm orchestration as Kimi Code CLI tools."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .models import AgentConfig, AgentPhase, SwarmTopology
from .orchestrator import SwarmOrchestrator, DEFAULT_STATE_PATH
from .display import KimiDisplay

mcp = FastMCP("kimi-swarm")

# Global orchestrator instance — persists across tool calls
_orch: SwarmOrchestrator | None = None
_state_path: Path = DEFAULT_STATE_PATH


def _get_orch() -> SwarmOrchestrator:
    """Get or restore the orchestrator."""
    global _orch
    if _orch is None:
        _orch = SwarmOrchestrator(state_path=_state_path)
        if not _orch.load_state():
            # Auto-init if no state exists and KIMI_SWARM_AUTO_INIT is set
            if os.environ.get("KIMI_SWARM_AUTO_INIT"):
                _orch.init_swarm()
    return _orch


def _status_to_todos(status: Any) -> list[dict[str, str]]:
    """Convert swarm status to a todo list for Kimi's sticky toolbar panel."""
    todos: list[dict[str, str]] = []
    header = f"🐝 {status.swarm_id[:12]} | {status.active_agents}/{status.max_agents} agents | {status.overall_progress:.0f}% done"
    todos.append({"title": header, "status": "in_progress"})

    for agent in status.agents:
        phase = agent.phase.value
        progress = agent.task.progress_percent if agent.task else 0.0
        if phase in ("completed", "terminated"):
            item_status = "done"
        elif phase in ("idle", "spawning"):
            item_status = "pending"
        else:
            item_status = "in_progress"

        bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        title = f"{agent.name} ({agent.agent_type}) — {phase} {bar} {progress:.0f}%"
        todos.append({"title": title, "status": item_status})

    if not status.agents:
        todos.append({"title": "No agents spawned yet — use agent_spawn to add agents", "status": "pending"})

    return todos


def _swarm_response(status: Any) -> dict[str, Any]:
    """Build a standard swarm response with markdown and todo-sync data."""
    return {
        "swarm_id": status.swarm_id,
        "topology": status.topology.value,
        "max_agents": status.max_agents,
        "active_agents": status.active_agents,
        "overall_progress": status.overall_progress,
        "completed_tasks": status.completed_tasks,
        "total_tasks": status.total_tasks,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def swarm_init(topology: str = "hierarchical", max_agents: int = 5) -> dict[str, Any]:
    """Initialize a new swarm with the given topology and max agents."""
    global _orch
    _orch = SwarmOrchestrator(topology=topology, max_agents=max_agents, state_path=_state_path)
    status = _orch.init_swarm()
    return _swarm_response(status)


@mcp.tool()
def swarm_status() -> dict[str, Any]:
    """Get the current swarm status as markdown for display."""
    orch = _get_orch()
    status = orch.get_status()
    return _swarm_response(status)


@mcp.tool()
def swarm_shutdown(clear_state: bool = False) -> dict[str, Any]:
    """Shutdown the swarm and optionally clear persisted state."""
    global _orch
    orch = _get_orch()
    status = orch.shutdown()
    result = {
        "swarm_id": status.swarm_id,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }
    if clear_state:
        orch.clear_state()
        _orch = None
    return result


@mcp.tool()
def agent_spawn(
    agent_type: str,
    name: str,
    model: str = "inherit",
    domain: str = "",
    task: str = "",
) -> dict[str, Any]:
    """Spawn a new agent in the swarm."""
    orch = _get_orch()
    config = AgentConfig(type=agent_type, name=name, model=model, domain=domain, task=task)
    agent = orch.spawn_agent(config)
    status = orch.get_status()
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "type": agent.agent_type,
        "model": agent.model,
        "resolved_model": agent.resolved_model,
        "phase": agent.phase.value,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_execute(agent_id: str, prompt: str) -> dict[str, Any]:
    """Execute a task on an agent."""
    orch = _get_orch()
    result = orch.execute_task(agent_id, prompt)
    status = orch.get_status()
    return {
        "agent_id": agent_id,
        "status": result.get("status"),
        "mode": result.get("mode", "native_kimi"),
        "result": result.get("result", ""),
        "tokens": result.get("tokens", {}),
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_assign(agent_id: str, task_description: str) -> dict[str, Any]:
    """Assign a task to an agent."""
    orch = _get_orch()
    task = orch.assign_task(agent_id, task_description)
    status = orch.get_status()
    return {
        "agent_id": agent_id,
        "task_id": task.task_id,
        "description": task.description,
        "status": task.status,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_progress(agent_id: str, percent: float) -> dict[str, Any]:
    """Update an agent's progress (0-100)."""
    orch = _get_orch()
    orch.update_agent_progress(agent_id, percent)
    status = orch.get_status()
    return {
        "agent_id": agent_id,
        "progress": percent,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_phase(agent_id: str, phase: str) -> dict[str, Any]:
    """Set an agent's phase."""
    orch = _get_orch()
    orch.set_agent_phase(agent_id, phase)
    status = orch.get_status()
    return {
        "agent_id": agent_id,
        "phase": phase,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_terminate(agent_id: str) -> dict[str, Any]:
    """Terminate an agent."""
    orch = _get_orch()
    orch.terminate_agent(agent_id)
    status = orch.get_status()
    return {
        "agent_id": agent_id,
        "status": "terminated",
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_list() -> dict[str, Any]:
    """List all agents in the swarm."""
    orch = _get_orch()
    agents = orch.list_agents()
    status = orch.get_status()
    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "type": a.agent_type,
                "model": a.model,
                "resolved_model": a.resolved_model,
                "phase": a.phase.value,
                "progress": a.task.progress_percent if a.task else 0.0,
                "tokens_total": a.tokens.total_tokens,
            }
            for a in agents
        ],
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def swarm_demo() -> dict[str, Any]:
    """Run a quick demo swarm and return the final status."""
    orch = SwarmOrchestrator(topology="hierarchical", max_agents=5, state_path=_state_path)
    orch.init_swarm()

    configs = [
        AgentConfig(type="architect", name="architect-1", model="sonnet"),
        AgentConfig(type="coder", name="coder-1", model="sonnet"),
        AgentConfig(type="coder", name="coder-2", model="haiku"),
        AgentConfig(type="tester", name="tester-1", model="haiku"),
        AgentConfig(type="reviewer", name="reviewer-1", model="sonnet"),
    ]
    for cfg in configs:
        orch.spawn_agent(cfg)

    tasks = [
        ("coder-1", "Implement user authentication module"),
        ("coder-2", "Create database schema"),
        ("tester-1", "Write unit tests"),
        ("reviewer-1", "Review authentication implementation"),
    ]
    for name, task in tasks:
        agent_id = next(a.agent_id for a in orch.list_agents() if a.name == name)
        orch.execute_task(agent_id, task)

    orch.update_agent_progress(agent_id, 75.0)
    status = orch.get_status()
    markdown = KimiDisplay.status_to_markdown(status)
    orch.shutdown()
    orch.clear_state()
    return {"markdown": markdown, "swarm_id": status.swarm_id, "todos": _status_to_todos(status)}


def main() -> None:
    """Run the MCP server over stdio."""
    # Allow overriding state path via env var
    global _state_path
    if path := os.environ.get("KIMI_SWARM_STATE_PATH"):
        _state_path = Path(path)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
