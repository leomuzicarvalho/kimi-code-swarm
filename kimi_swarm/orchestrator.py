"""Core swarm orchestration logic."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    AgentConfig,
    AgentPhase,
    AgentStatus,
    ContextWindow,
    SwarmStatus,
    SwarmTopology,
    TaskInfo,
    TokenUsage,
)
from .mcp_client import SwarmMCPClient
from . import model_mapping


DEFAULT_STATE_PATH = Path.home() / ".kimi" / "kimi-swarm-state.json"


class SwarmOrchestrator:
    """Orchestrates a swarm of agents with lifecycle management."""

    def __init__(
        self,
        topology: SwarmTopology | str = SwarmTopology.HIERARCHICAL,
        max_agents: int = 5,
        state_path: Path | str | None = None,
    ) -> None:
        self.topology = SwarmTopology(topology) if isinstance(topology, str) else topology
        self.max_agents = max_agents
        self.swarm_id: str = ""
        self._agents: dict[str, AgentStatus] = {}
        self._client = SwarmMCPClient()
        self._is_active = False
        self._main_context = ContextWindow(used_tokens=0, max_tokens=128000)
        self._state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        self.entry_point_agent_id: str = ""

    def init_swarm(self) -> SwarmStatus:
        """Initialize the swarm via MCP."""
        result = self._client.swarm_init(
            topology=self.topology.value,
            max_agents=self.max_agents,
        )
        self.swarm_id = result.get("swarm_id", f"swarm-{uuid.uuid4().hex[:8]}")
        self._is_active = True
        self.save_state()
        return self.get_status()

    def spawn_agent(self, config: AgentConfig) -> AgentStatus:
        """Spawn a new agent in the swarm."""
        if len(self._agents) >= self.max_agents:
            raise RuntimeError(f"Max agents ({self.max_agents}) reached")

        result = self._client.agent_spawn(config)
        agent_id = result.get("agent_id", f"agent-{uuid.uuid4().hex[:8]}")

        # Resolve model alias → actual Kimi model
        resolved = model_mapping.resolve_kimi_model(config.model)
        max_tokens = model_mapping.get_context_size(config.model)

        agent = AgentStatus(
            agent_id=agent_id,
            name=config.name,
            agent_type=config.type,
            model=config.model,
            resolved_model=resolved,
            phase=AgentPhase.IDLE,
            context=ContextWindow(used_tokens=0, max_tokens=max_tokens),
        )
        self._agents[agent_id] = agent
        # First spawned agent becomes the entry-point agent
        if not self.entry_point_agent_id:
            self.entry_point_agent_id = agent_id
        self.save_state()
        return agent

    def assign_task(self, agent_id: str, task_description: str) -> TaskInfo:
        """Assign a task to an agent."""
        agent = self._get_agent(agent_id)
        task = TaskInfo(description=task_description, status="pending")
        agent.task = task
        agent.phase = AgentPhase.PLANNING
        agent.last_active = datetime.now()
        self.save_state()
        return task

    def execute_task(self, agent_id: str, prompt: str) -> dict[str, Any]:
        """Execute a task on an agent."""
        agent = self._get_agent(agent_id)
        if agent.task is None:
            self.assign_task(agent_id, prompt)

        agent.phase = AgentPhase.EXECUTING
        agent.task.status = "in_progress"
        agent.last_active = datetime.now()

        result = self._client.agent_execute(agent_id, prompt)

        # Update token usage
        tokens = result.get("tokens", {})
        agent.tokens.add(
            prompt=tokens.get("prompt", 0),
            completion=tokens.get("completion", 0),
        )
        agent.context.update(agent.tokens.total_tokens)
        agent.messages_count += 1

        # Update task
        if agent.task:
            agent.task.status = "completed" if result.get("status") == "completed" else "failed"
            agent.task.result = result.get("result", "")
            agent.task.progress_percent = 100.0 if result.get("status") == "completed" else 0.0
            agent.task.completed_at = datetime.now()

        agent.phase = AgentPhase.COMPLETED if result.get("status") == "completed" else AgentPhase.FAILED
        self.save_state()
        return result

    def update_agent_progress(self, agent_id: str, progress: float) -> None:
        """Manually update an agent's task progress."""
        agent = self._get_agent(agent_id)
        if agent.task:
            agent.task.progress_percent = max(0.0, min(100.0, progress))
        self.save_state()

    def set_agent_phase(self, agent_id: str, phase: AgentPhase | str) -> None:
        """Set an agent's phase manually."""
        agent = self._get_agent(agent_id)
        agent.phase = AgentPhase(phase) if isinstance(phase, str) else phase
        agent.last_active = datetime.now()
        self.save_state()

    def get_agent(self, agent_id: str) -> AgentStatus:
        """Get a single agent's status."""
        return self._get_agent(agent_id)

    def list_agents(self) -> list[AgentStatus]:
        """List all agents."""
        return list(self._agents.values())

    def terminate_agent(self, agent_id: str) -> None:
        """Terminate an agent."""
        agent = self._get_agent(agent_id)
        self._client.agent_terminate(agent_id)
        agent.phase = AgentPhase.TERMINATED
        self.save_state()

    def shutdown(self) -> SwarmStatus:
        """Shutdown the entire swarm."""
        if self.swarm_id:
            self._client.swarm_shutdown(self.swarm_id)
        self._is_active = False
        for agent in self._agents.values():
            if agent.phase not in (AgentPhase.TERMINATED, AgentPhase.FAILED):
                agent.phase = AgentPhase.TERMINATED
        self.save_state()
        return self.get_status()

    def get_status(self) -> SwarmStatus:
        """Get the full swarm status."""
        # Estimate main agent context based on orchestration overhead
        main_used = sum(a.tokens.total_tokens for a in self._agents.values()) + 2000
        self._main_context.update(main_used)

        return SwarmStatus(
            swarm_id=self.swarm_id or "not-initialized",
            topology=self.topology,
            max_agents=self.max_agents,
            agents=list(self._agents.values()),
            main_context=self._main_context,
            is_active=self._is_active,
            entry_point_agent_id=self.entry_point_agent_id,
        )

    def update_main_context(self, used_tokens: int) -> None:
        """Update the main agent's context window tracking."""
        self._main_context.update(used_tokens)

    def save_state(self) -> None:
        """Persist swarm state to disk."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        status = self.get_status()
        data = status.to_dict()
        with open(self._state_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load_state(self) -> bool:
        """Load swarm state from disk. Returns True if loaded successfully."""
        if not self._state_path.exists():
            return False
        try:
            with open(self._state_path, "r") as f:
                data = json.load(f)
            status = SwarmStatus.from_dict(data)
            self.swarm_id = status.swarm_id
            self.topology = status.topology
            self.max_agents = status.max_agents
            self._agents = {a.agent_id: a for a in status.agents}
            self._main_context = status.main_context
            self._is_active = status.is_active
            self.entry_point_agent_id = status.entry_point_agent_id
            return True
        except Exception:
            return False

    def clear_state(self) -> None:
        """Remove persisted state file."""
        if self._state_path.exists():
            self._state_path.unlink()

    def get_entry_point_agent(self) -> AgentStatus | None:
        """Return the swarm's entry-point (coordinator) agent, or None."""
        if self.entry_point_agent_id and self.entry_point_agent_id in self._agents:
            return self._agents[self.entry_point_agent_id]
        return None

    def _get_agent(self, agent_id: str) -> AgentStatus:
        if agent_id not in self._agents:
            raise KeyError(f"Agent {agent_id} not found")
        return self._agents[agent_id]

    @staticmethod
    def _model_to_context_size(model: str) -> int:
        """Map model name to context window size.
        
        Deprecated: use model_mapping.get_context_size() instead.
        """
        return model_mapping.get_context_size(model)
