"""Core swarm orchestration logic."""

from __future__ import annotations

import json
import os
import threading
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
    VerificationResult,
)
from .mcp_client import SwarmMCPClient
from . import model_mapping


DEFAULT_STATE_PATH = Path.home() / ".kimi" / "kimi-swarm-state.json"


class SwarmOrchestrator:
    """Orchestrates a swarm of agents with lifecycle management and agentic loop."""

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
        self.total_iterations: int = 0
        self._last_verification: VerificationResult | None = None
        self._dashboard_broadcast: Any | None = None  # injected from mcp_server
        self._bg_threads: dict[str, threading.Thread] = {}
        self._bg_results: dict[str, dict[str, Any]] = {}

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
        self._broadcast_now()
        return agent

    def assign_task(self, agent_id: str, task_description: str, max_attempts: int = 3) -> TaskInfo:
        """Assign a task to an agent."""
        agent = self._get_agent(agent_id)
        task = TaskInfo(
            description=task_description,
            status="pending",
            max_attempts=max_attempts,
        )
        agent.task = task
        agent.phase = AgentPhase.PLANNING
        agent.last_active = datetime.now()
        self.save_state()
        self._broadcast_now()
        return task

    def execute_task(self, agent_id: str, prompt: str) -> dict[str, Any]:
        """Execute a task on an agent."""
        agent = self._get_agent(agent_id)
        if agent.task is None:
            self.assign_task(agent_id, prompt)

        agent.phase = AgentPhase.EXECUTING
        agent.task.status = "in_progress"
        agent.last_active = datetime.now()
        self.save_state()
        self._broadcast_now()

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
        self._broadcast_now()
        return result

    def execute_with_verification(
        self,
        agent_id: str,
        prompt: str,
        verifier_agent_id: str | None = None,
        max_iterations: int = 3,
        verification_prompt: str = "",
    ) -> dict[str, Any]:
        """Execute a task with verification loop.

        Flow:
        1. Execute task on agent
        2. If verifier_agent_id provided, run verification
        3. If verification passes → return success
        4. If verification fails AND attempts < max_iterations:
           - Feed verification feedback back into the agent
           - Agent automatically retries with corrected instructions
           - Loop continues autonomously (main agent does NOT take over)
        5. If max iterations exceeded → return final failure
        """
        agent = self._get_agent(agent_id)
        if agent.task is None:
            self.assign_task(agent_id, prompt, max_attempts=max_iterations)

        task = agent.task
        assert task is not None

        for iteration in range(1, max_iterations + 1):
            self.total_iterations += 1
            task.attempt_count = iteration
            task.last_iteration_at = datetime.now()
            task.verification_status = "pending"
            task.status = "in_progress"
            task.progress_percent = ((iteration - 1) / max_iterations) * 100
            agent.phase = AgentPhase.EXECUTING
            self.save_state()
            self._broadcast_now()

            # Step 1: Execute
            exec_result = self._client.agent_execute(agent_id, prompt)
            tokens = exec_result.get("tokens", {})
            agent.tokens.add(
                prompt=tokens.get("prompt", 0),
                completion=tokens.get("completion", 0),
            )
            agent.context.update(agent.tokens.total_tokens)
            agent.messages_count += 1

            task.result = exec_result.get("result", "")
            task.progress_percent = ((iteration - 0.5) / max_iterations) * 100
            self.save_state()
            self._broadcast_now()

            # Step 2: Verify (if verifier provided)
            if verifier_agent_id and verifier_agent_id in self._agents:
                verifier = self._agents[verifier_agent_id]
                verifier.phase = AgentPhase.REVIEWING
                verifier.last_active = datetime.now()
                self.save_state()
                self._broadcast_now()

                # Build a verification prompt that tells the verifier exactly where
                # the agent's workspace is so it can inspect real files.
                agent_workspace = ""
                if hasattr(self._client, "_work_dirs"):
                    agent_workspace = str(self._client._work_dirs.get(agent_id, ""))

                workspace_hint = ""
                if agent_workspace:
                    workspace_hint = (
                        f"\n\nAgent workspace (check files here): {agent_workspace}\n"
                        f"List files in this directory and verify any claimed outputs."
                    )

                if verification_prompt:
                    verify_prompt = verification_prompt + workspace_hint
                else:
                    verify_prompt = (
                        f"Verify the following task result. Task: {task.description}\n"
                        f"Result: {task.result}\n"
                        f"Iteration: {iteration}/{max_iterations}"
                        f"{workspace_hint}\n"
                        f"Check: 1) correctness, 2) completeness, 3) web UI state freshness. "
                        f"Respond with PASSED or FAILED and detailed feedback."
                    )
                verify_result = self._client.agent_execute(verifier_agent_id, verify_prompt)

                verifier.tokens.add(
                    prompt=verify_result.get("tokens", {}).get("prompt", 0),
                    completion=verify_result.get("tokens", {}).get("completion", 0),
                )
                verifier.context.update(verifier.tokens.total_tokens)
                verifier.messages_count += 1

                # Parse verification result — accept various approval keywords
                v_text = str(verify_result.get("result", "")).upper()
                has_approval = any(k in v_text for k in ("PASSED", "PASS", "APPROVED", "OK", "SUCCESS", "CORRECT"))
                has_rejection = "FAILED" in v_text or "FAIL" in v_text
                passed = has_approval and not has_rejection
                feedback = verify_result.get("result", "")

                # Check web UI freshness
                web_ui_ok = self._verify_web_ui_state()

                verification = VerificationResult(
                    passed=passed,
                    feedback=feedback,
                    web_ui_ok=web_ui_ok,
                    web_ui_details="State file fresh" if web_ui_ok else "State file stale",
                    iteration_number=iteration,
                )
                self._last_verification = verification
                task.verification_status = "passed" if passed else "failed"
                task.verification_feedback = feedback

                verifier.phase = AgentPhase.COMPLETED if passed else AgentPhase.WAITING
                self.save_state()
                self._broadcast_now()

                if passed:
                    task.status = "completed"
                    task.progress_percent = 100.0
                    task.completed_at = datetime.now()
                    agent.phase = AgentPhase.COMPLETED
                    self.save_state()
                    self._broadcast_now()
                    return {
                        "status": "completed",
                        "agent_id": agent_id,
                        "iteration": iteration,
                        "verification": verification.to_dict(),
                        "result": task.result,
                        "tokens": agent.tokens.to_dict(),
                    }

                # Verification failed - auto-retry with feedback if iterations remain
                if iteration < max_iterations:
                    agent.phase = AgentPhase.PLANNING
                    task.status = "pending"
                    # Build corrected prompt that includes the original task + verifier feedback
                    feedback_payload = (
                        f"\n\n🔁 **AGENTIC LOOP — Iteration {iteration}/{max_iterations} FAILED**\n\n"
                        f"**Agent:** `{agent.name}` (`{agent_id}`)\n"
                        f"**Task:** {task.description}\n\n"
                        f"**Verification Feedback:**\n{feedback}\n\n"
                        f"**Web UI Status:** {'✅ Fresh' if web_ui_ok else '❌ Stale'}\n\n"
                        f"**Action:** Auto-retrying with corrected instructions."
                    )
                    task.result = task.result + feedback_payload
                    # Update prompt for next iteration so the agent gets the feedback
                    prompt = (
                        f"[CORRECTED TASK — Iteration {iteration + 1}/{max_iterations}]\n\n"
                        f"Original task: {task.description}\n\n"
                        f"Previous attempt result: {task.result}\n\n"
                        f"Verification feedback (MUST address all points):\n{feedback}\n\n"
                        f"Please correct the issues and complete the task."
                    )
                    self.save_state()
                    self._broadcast_now()
                    # Continue to next iteration — main agent does NOT take over
                    continue

            else:
                # No verifier - just check execution status
                if exec_result.get("status") == "completed":
                    task.status = "completed"
                    task.progress_percent = 100.0
                    task.completed_at = datetime.now()
                    task.verification_status = "passed"
                    agent.phase = AgentPhase.COMPLETED
                    self.save_state()
                    self._broadcast_now()
                    return {
                        "status": "completed",
                        "agent_id": agent_id,
                        "iteration": iteration,
                        "result": task.result,
                        "tokens": agent.tokens.to_dict(),
                    }

        # Max iterations exceeded
        task.status = "failed"
        task.progress_percent = 100.0
        agent.phase = AgentPhase.FAILED
        final_feedback = (
            f"\n\n❌ **AGENTIC LOOP — MAX ITERATIONS ({max_iterations}) EXCEEDED**\n\n"
            f"**Agent:** `{agent.name}` (`{agent_id}`)\n"
            f"**Task:** {task.description}\n\n"
            f"**Final Verification Feedback:** {task.verification_feedback}\n\n"
            f"**Action Required:** Route to entry-point agent for manual review or reassignment."
        )
        task.result = task.result + final_feedback
        self.save_state()
        self._broadcast_now()
        return {
            "status": "failed",
            "agent_id": agent_id,
            "iteration": max_iterations,
            "max_iterations": max_iterations,
            "verification": self._last_verification.to_dict() if self._last_verification else None,
            "result": task.result,
            "route_to_entry_point": self.entry_point_agent_id,
            "needs_retry": False,
        }

    def execute_task_async(self, agent_id: str, prompt: str) -> dict[str, Any]:
        """Execute a task in a background thread so the caller isn't blocked.

        Returns immediately with an 'accepted' status. The actual result is
        stored and can be retrieved via agent_status() or swarm_status().
        """
        agent = self._get_agent(agent_id)

        # Kill any existing background thread for this agent
        self._kill_bg_thread(agent_id)

        agent.phase = AgentPhase.EXECUTING
        agent.last_active = datetime.now()
        if agent.task is None:
            self.assign_task(agent_id, prompt)
        agent.task.status = "in_progress"
        self.save_state()
        self._broadcast_now()

        def _run() -> None:
            try:
                result = self.execute_task(agent_id, prompt)
                self._bg_results[agent_id] = result
            except Exception as exc:
                self._bg_results[agent_id] = {
                    "status": "failed",
                    "agent_id": agent_id,
                    "result": str(exc),
                }

        t = threading.Thread(target=_run, daemon=True)
        self._bg_threads[agent_id] = t
        t.start()

        return {
            "status": "accepted",
            "agent_id": agent_id,
            "message": f"Task accepted for {agent.name}. Use swarm_status() or agent_status() to monitor progress.",
        }

    def execute_with_verification_async(
        self,
        agent_id: str,
        prompt: str,
        verifier_agent_id: str | None = None,
        max_iterations: int = 3,
        verification_prompt: str = "",
    ) -> dict[str, Any]:
        """Run the verification loop in a background thread.

        Returns immediately with an 'accepted' status.
        """
        agent = self._get_agent(agent_id)
        self._kill_bg_thread(agent_id)

        agent.phase = AgentPhase.EXECUTING
        agent.last_active = datetime.now()
        if agent.task is None:
            self.assign_task(agent_id, prompt, max_attempts=max_iterations)
        agent.task.status = "in_progress"
        self.save_state()
        self._broadcast_now()

        def _run() -> None:
            try:
                result = self.execute_with_verification(
                    agent_id=agent_id,
                    prompt=prompt,
                    verifier_agent_id=verifier_agent_id,
                    max_iterations=max_iterations,
                    verification_prompt=verification_prompt,
                )
                self._bg_results[agent_id] = result
            except Exception as exc:
                self._bg_results[agent_id] = {
                    "status": "failed",
                    "agent_id": agent_id,
                    "result": str(exc),
                }

        t = threading.Thread(target=_run, daemon=True)
        self._bg_threads[agent_id] = t
        t.start()

        return {
            "status": "accepted",
            "agent_id": agent_id,
            "message": (
                f"Verification loop accepted for {agent.name} "
                f"(up to {max_iterations} iterations). "
                f"Use swarm_status() or agent_status() to monitor progress."
            ),
        }

    def _kill_bg_thread(self, agent_id: str) -> None:
        """Stop an existing background thread for an agent."""
        old = self._bg_threads.pop(agent_id, None)
        if old and old.is_alive():
            # We can't truly kill a Python thread, but we can mark the agent
            # as terminated so the next loop iteration exits early
            try:
                agent = self._get_agent(agent_id)
                agent.phase = AgentPhase.TERMINATED
            except KeyError:
                pass

    def get_bg_result(self, agent_id: str) -> dict[str, Any] | None:
        """Get the result of a background task if it has completed."""
        return self._bg_results.get(agent_id)

    def acknowledge_failure(self, agent_id: str) -> dict[str, Any]:
        """Main agent acknowledges a failure, digests loop info, and prepares for reassignment.

        This should be called on the entry-point agent after receiving a failed loop result.
        Returns a structured payload with all iteration history for the next assignment.
        """
        agent = self._get_agent(agent_id)
        if agent.task is None:
            return {"status": "error", "message": "No task found for agent"}

        task = agent.task
        history = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "task_description": task.description,
            "attempt_count": task.attempt_count,
            "max_attempts": task.max_attempts,
            "verification_status": task.verification_status,
            "verification_feedback": task.verification_feedback,
            "last_result": task.result,
            "total_swarm_iterations": self.total_iterations,
            "acknowledged_at": datetime.now().isoformat(),
        }

        agent.phase = AgentPhase.PLANNING
        agent.last_active = datetime.now()
        agent.metadata["failure_acknowledged"] = history
        self.save_state()
        self._broadcast_now()

        return {
            "status": "acknowledged",
            "message": (
                f"Failure acknowledged for {agent.name}. "
                f"Attempt {task.attempt_count}/{task.max_attempts} digested. "
                f"Ready to reassign to entry-point or another agent with feedback."
            ),
            "history": history,
            "entry_point_agent_id": self.entry_point_agent_id,
        }

    def reassign_with_feedback(self, from_agent_id: str, to_agent_id: str, corrected_prompt: str) -> dict[str, Any]:
        """Reassign a corrected task from one agent to another, carrying forward feedback history."""
        from_agent = self._get_agent(from_agent_id)
        to_agent = self._get_agent(to_agent_id)

        if from_agent.task is None:
            return {"status": "error", "message": "No task to reassign"}

        old_task = from_agent.task
        new_task = TaskInfo(
            description=corrected_prompt,
            status="pending",
            max_attempts=old_task.max_attempts,
            attempt_count=old_task.attempt_count,
            verification_status="pending",
            verification_feedback=old_task.verification_feedback,
        )
        # Carry forward metadata and feedback
        if "failure_acknowledged" in from_agent.metadata:
            new_task.result = (
                f"[PREVIOUS ITERATION HISTORY]\n"
                f"{json.dumps(from_agent.metadata['failure_acknowledged'], indent=2)}\n\n"
                f"[VERIFICATION FEEDBACK]\n{old_task.verification_feedback}\n\n"
                f"[CORRECTED TASK]\n{corrected_prompt}"
            )

        to_agent.task = new_task
        to_agent.phase = AgentPhase.PLANNING
        to_agent.last_active = datetime.now()
        self.save_state()
        self._broadcast_now()

        return {
            "status": "reassigned",
            "from_agent": from_agent.name,
            "to_agent": to_agent.name,
            "task": new_task.to_dict(),
        }

    def update_agent_progress(self, agent_id: str, progress: float) -> None:
        """Manually update an agent's task progress."""
        agent = self._get_agent(agent_id)
        if agent.task:
            agent.task.progress_percent = max(0.0, min(100.0, progress))
        self.save_state()
        self._broadcast_now()

    def set_agent_phase(self, agent_id: str, phase: AgentPhase | str) -> None:
        """Set an agent's phase manually."""
        agent = self._get_agent(agent_id)
        agent.phase = AgentPhase(phase) if isinstance(phase, str) else phase
        agent.last_active = datetime.now()
        self.save_state()
        self._broadcast_now()

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
        self._broadcast_now()

    def shutdown(self) -> SwarmStatus:
        """Shutdown the entire swarm."""
        if self.swarm_id:
            self._client.swarm_shutdown(self.swarm_id)
        self._is_active = False
        for agent in self._agents.values():
            if agent.phase not in (AgentPhase.TERMINATED, AgentPhase.FAILED):
                agent.phase = AgentPhase.TERMINATED
        self.save_state()
        self._broadcast_now()
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
            total_iterations=self.total_iterations,
            last_verification=self._last_verification,
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
            self.total_iterations = status.total_iterations
            self._last_verification = status.last_verification
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

    def set_dashboard_broadcast(self, broadcast_fn: Any) -> None:
        """Inject a dashboard broadcast function for immediate updates."""
        self._dashboard_broadcast = broadcast_fn

    def _broadcast_now(self) -> None:
        """Trigger immediate dashboard broadcast if available."""
        if self._dashboard_broadcast is not None:
            try:
                self._dashboard_broadcast()
            except Exception:
                pass

    def _verify_web_ui_state(self) -> bool:
        """Check if the state file has been updated recently (within 5 seconds)."""
        try:
            if self._state_path.exists():
                mtime = self._state_path.stat().st_mtime
                return (datetime.now().timestamp() - mtime) < 5.0
        except Exception:
            pass
        return False

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
