"""Local MCP client for swarm orchestration."""

from __future__ import annotations

import json
import os
from typing import Any

from .models import AgentConfig, AgentStatus, AgentPhase, TaskInfo, TokenUsage, ContextWindow


class SwarmMCPClient:
    """Local MCP client — simulates agent execution for workflow building and testing."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._call_count = 0

    def swarm_init(self, topology: str, max_agents: int) -> dict[str, Any]:
        return {
            "swarm_id": f"swarm-{os.urandom(4).hex()}",
            "topology": topology,
            "max_agents": max_agents,
            "status": "initialized",
        }

    def agent_spawn(self, config: AgentConfig) -> dict[str, Any]:
        agent_id = f"agent-{os.urandom(4).hex()}"
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "name": config.name,
            "type": config.type,
            "model": config.model,
            "status": "idle",
            "task": None,
        }
        return {"agent_id": agent_id, "status": "spawned"}

    def agent_execute(self, agent_id: str, prompt: str) -> dict[str, Any]:
        self._call_count += 1
        # Simulate token usage based on prompt length
        prompt_tokens = len(prompt.split())
        completion_tokens = prompt_tokens // 2
        return {
            "agent_id": agent_id,
            "status": "completed",
            "mode": "native_kimi",
            "prompt": prompt,
            "result": f"Completed: {prompt[:50]}...",
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
        }

    def agent_status(self, agent_id: str) -> dict[str, Any]:
        return self._agents.get(agent_id, {"status": "unknown"})

    def agent_list(self) -> list[dict[str, Any]]:
        return list(self._agents.values())

    def agent_terminate(self, agent_id: str) -> dict[str, Any]:
        if agent_id in self._agents:
            self._agents[agent_id]["status"] = "terminated"
        return {"agent_id": agent_id, "status": "terminated"}

    def swarm_shutdown(self, swarm_id: str) -> dict[str, Any]:
        return {"swarm_id": swarm_id, "status": "shutdown"}

    def memory_store(self, namespace: str, key: str, value: str) -> dict[str, Any]:
        return {"status": "stored", "namespace": namespace, "key": key}

    def memory_search(self, namespace: str, query: str) -> list[dict[str, Any]]:
        return []
