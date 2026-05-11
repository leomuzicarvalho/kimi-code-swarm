"""Local MCP client for swarm orchestration."""

from __future__ import annotations

import json
import os
import random
from typing import Any

from .models import AgentConfig, AgentStatus, AgentPhase, TaskInfo, TokenUsage, ContextWindow


class SwarmMCPClient:
    """Local MCP client — simulates agent execution with configurable realism."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._call_count = 0
        self._failure_rate = float(os.environ.get("KIMI_SWARM_SIM_FAILURE_RATE", "0.0"))
        self._verify_failure_rate = float(os.environ.get("KIMI_SWARM_SIM_VERIFY_FAILURE_RATE", "0.0"))

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

        # Determine if this should simulate a failure
        # Verifier prompts get different failure rate
        is_verification = "verify" in prompt.lower() or "verification" in prompt.lower()
        fail_rate = self._verify_failure_rate if is_verification else self._failure_rate
        should_fail = random.random() < fail_rate

        if should_fail:
            result_text = (
                f"FAILED: Simulated failure for task '{prompt[:50]}...'. "
                f"The output did not meet requirements. Please review and retry."
            )
            if is_verification:
                result_text = (
                    f"FAILED: Verification did not pass. Issues found with '{prompt[:50]}...'. "
                    f"Please review and retry."
                )
            return {
                "agent_id": agent_id,
                "status": "failed",
                "mode": "native_kimi",
                "prompt": prompt,
                "result": result_text,
                "tokens": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                },
            }

        result_text = f"Completed: {prompt[:100]}..."
        if is_verification:
            result_text = f"PASSED: Verification completed successfully for '{prompt[:50]}...'. All checks passed."
        return {
            "agent_id": agent_id,
            "status": "completed",
            "mode": "native_kimi",
            "prompt": prompt,
            "result": result_text,
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
