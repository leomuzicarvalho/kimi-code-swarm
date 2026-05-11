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
from .web_dashboard import launch_persistent_dashboard, stop_persistent_dashboard, stop_all_dashboards, broadcast_now

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
        # Wire up immediate dashboard broadcast
        _orch.set_dashboard_broadcast(lambda: broadcast_now(state_path=_state_path))
    return _orch


def _status_to_todos(status: Any) -> list[dict[str, str]]:
    """Convert swarm status to a todo list for Kimi's sticky toolbar panel."""
    todos: list[dict[str, str]] = []
    header = f"🐝 {status.swarm_id[:12]} | {status.active_agents}/{status.max_agents} agents | {status.overall_progress:.0f}% done"
    if status.total_iterations:
        header += f" | {status.total_iterations} iter"
    if status.last_verification and not status.last_verification.passed:
        header += " ⚠️"
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
        if agent.task and agent.task.attempt_count > 0:
            title += f" (attempt {agent.task.attempt_count}/{agent.task.max_attempts})"
        if agent.task and agent.task.verification_status == "failed":
            title += " ❌ verify"
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
        "total_iterations": status.total_iterations,
        "last_verification": status.last_verification.to_dict() if status.last_verification else None,
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def swarm_init(topology: str = "hierarchical", max_agents: int = 5) -> dict[str, Any]:
    """Initialize a new swarm with the given topology and max agents.

    Automatically cleans up any existing swarm and launches the live web
    dashboard (re-using an existing dashboard process when available).
    """
    global _orch

    # Cleanup any existing swarm
    if _orch is not None:
        try:
            _orch.shutdown()
            _orch.clear_state()
        except Exception:
            pass
        _orch = None

    # Ensure stale state file is removed even if _orch was None
    if _state_path.exists():
        try:
            _state_path.unlink()
        except Exception:
            pass

    # Stop any existing dashboards before starting fresh
    try:
        stop_all_dashboards(state_path=_state_path)
    except Exception:
        pass

    _orch = SwarmOrchestrator(topology=topology, max_agents=max_agents, state_path=_state_path)
    status = _orch.init_swarm()
    _orch.set_dashboard_broadcast(lambda: broadcast_now(state_path=_state_path))

    # Auto-launch dashboard — idempotent: won't spawn duplicate servers or tabs
    try:
        launch_persistent_dashboard(port=0, state_path=_state_path, open_browser=True)
    except Exception:
        pass  # Dashboard is optional; don't fail init if browser/server fails

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
    """Execute a task on an agent.

    If the agent fails, do NOT take over the task yourself. Keep the swarm
    cycle alive by routing the failure to the entry-point agent using
    agent_execute or agent_assign so it can coordinate reassignment.
    """
    orch = _get_orch()
    try:
        result = orch.execute_task(agent_id, prompt)
    except Exception as exc:
        # Graceful failure — never let a tool exception break the swarm cycle
        result = {
            "status": "failed",
            "mode": "native_kimi",
            "result": str(exc),
            "tokens": {},
        }

    status = orch.get_status()
    markdown = KimiDisplay.status_to_markdown(status)

    # If the agent failed, append explicit guidance to keep the swarm cycle alive
    if result.get("status") != "completed":
        ep = orch.get_entry_point_agent()
        if ep:
            guidance = (
                f"\n\n⚠️ **Agent `{agent_id}` task failed.**\n\n"
                f"**Do NOT take over this task yourself.** To keep the swarm cycle alive, "
                f"route this failure to the entry-point agent `{ep.name}` (`{ep.agent_id}`) "
                f"using `agent_execute(agent_id='{ep.agent_id}', prompt='...')` or "
                f"`agent_assign(agent_id='{ep.agent_id}', task_description='...')` for "
                f"coordination and reassignment."
            )
        else:
            guidance = (
                f"\n\n⚠️ **Agent `{agent_id}` task failed.**\n\n"
                f"**Do NOT take over this task yourself.** To keep the swarm cycle alive, "
                f"spawn a coordinator agent and route this failure to it for reassignment."
            )
        markdown = markdown + guidance

    return {
        "agent_id": agent_id,
        "status": result.get("status"),
        "mode": result.get("mode", "native_kimi"),
        "result": result.get("result", ""),
        "tokens": result.get("tokens", {}),
        "markdown": markdown,
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_execute_with_verification(
    agent_id: str,
    prompt: str,
    verifier_agent_id: str = "",
    max_iterations: int = 3,
    verification_prompt: str = "",
) -> dict[str, Any]:
    """Execute a task with automatic verification loop.

    Flow:
    1. Task executes on agent_id
    2. If verifier_agent_id is provided, verification runs
    3. If verification passes → success
    4. If verification fails AND iterations remain:
       - Failure is acknowledged
       - Feedback is stored
       - Result includes route_to_entry_point for reassignment
    5. If max iterations exceeded → final failure

    After EVERY iteration, the web dashboard is updated.
    """
    orch = _get_orch()
    verifier_id = verifier_agent_id if verifier_agent_id else None

    try:
        result = orch.execute_with_verification(
            agent_id=agent_id,
            prompt=prompt,
            verifier_agent_id=verifier_id,
            max_iterations=max_iterations,
            verification_prompt=verification_prompt,
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "agent_id": agent_id,
            "iteration": 0,
            "result": str(exc),
            "route_to_entry_point": orch.entry_point_agent_id,
            "needs_retry": False,
        }

    status = orch.get_status()
    markdown = KimiDisplay.status_to_markdown(status)

    # Build loop-aware markdown
    iter_info = result.get("iteration", 1)
    max_iter = result.get("max_iterations", max_iterations)
    verif = result.get("verification")

    if result.get("status") == "completed":
        loop_md = (
            f"\n\n✅ **Agentic Loop Complete** — Iteration {iter_info}/{max_iter}\n"
            f"- Agent: `{agent_id}`\n"
            f"- Verification: {'PASSED' if verif and verif.get('passed') else 'N/A'}\n"
            f"- Web UI: {'✅ Updated' if verif and verif.get('web_ui_ok') else '❌ Stale'}\n"
        )
    elif result.get("needs_retry"):
        ep = orch.get_entry_point_agent()
        loop_md = (
            f"\n\n🔁 **Agentic Loop — Retry Required** — Iteration {iter_info}/{max_iter}\n"
            f"- Agent: `{agent_id}`\n"
            f"- Verification: ❌ FAILED\n"
            f"- Feedback: {verif.get('feedback', 'N/A')[:200] if verif else 'N/A'}\n"
            f"- Web UI: {'✅ Updated' if verif and verif.get('web_ui_ok') else '❌ Stale'}\n"
            f"- **Next:** Route to entry-point `{ep.name if ep else 'N/A'}` "
            f"(`{result.get('route_to_entry_point', 'N/A')}`) for reassignment\n"
        )
    else:
        loop_md = (
            f"\n\n❌ **Agentic Loop — Max Iterations Exceeded** ({max_iter})\n"
            f"- Agent: `{agent_id}`\n"
            f"- Final verification: FAILED\n"
            f"- **Action:** Manual review or reassignment required\n"
        )

    return {
        "agent_id": agent_id,
        "status": result.get("status"),
        "iteration": iter_info,
        "max_iterations": max_iter,
        "verification": verif,
        "result": result.get("result", ""),
        "route_to_entry_point": result.get("route_to_entry_point", ""),
        "needs_retry": result.get("needs_retry", False),
        "markdown": markdown + loop_md,
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_acknowledge_failure(agent_id: str) -> dict[str, Any]:
    """Acknowledge a failure on an agent and digest iteration history.

    This is typically called on the entry-point agent after receiving
    a failed result from agent_execute_with_verification. It prepares
    the agent for reassignment with corrected instructions.
    """
    orch = _get_orch()
    try:
        result = orch.acknowledge_failure(agent_id)
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}

    status = orch.get_status()
    history = result.get("history", {})

    ack_md = ""
    if result.get("status") == "acknowledged":
        ack_md = (
            f"\n\n📋 **Failure Acknowledged**\n"
            f"- Agent: `{history.get('agent_name', agent_id)}`\n"
            f"- Attempt: {history.get('attempt_count', 0)}/{history.get('max_attempts', 3)}\n"
            f"- Verification: {history.get('verification_status', 'unknown')}\n"
            f"- Ready for reassignment with feedback digested\n"
        )

    return {
        "agent_id": agent_id,
        "status": result.get("status"),
        "history": history,
        "entry_point_agent_id": result.get("entry_point_agent_id", ""),
        "markdown": KimiDisplay.status_to_markdown(status) + ack_md,
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def agent_reassign_with_feedback(from_agent_id: str, to_agent_id: str, corrected_prompt: str) -> dict[str, Any]:
    """Reassign a corrected task from one agent to another, carrying forward feedback.

    This is the final step of the agentic loop: after the entry-point agent
    acknowledges a failure, it reassigns the corrected task to a developer.
    """
    orch = _get_orch()
    try:
        result = orch.reassign_with_feedback(from_agent_id, to_agent_id, corrected_prompt)
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}

    status = orch.get_status()
    re_md = ""
    if result.get("status") == "reassigned":
        re_md = (
            f"\n\n🔄 **Task Reassigned**\n"
            f"- From: `{result.get('from_agent', from_agent_id)}`\n"
            f"- To: `{result.get('to_agent', to_agent_id)}`\n"
            f"- Next: Execute with `agent_execute(agent_id='{to_agent_id}', prompt='...')`\n"
        )

    return {
        "from_agent_id": from_agent_id,
        "to_agent_id": to_agent_id,
        "status": result.get("status"),
        "task": result.get("task"),
        "markdown": KimiDisplay.status_to_markdown(status) + re_md,
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
                "attempt_count": a.task.attempt_count if a.task else 0,
                "verification_status": a.task.verification_status if a.task else "pending",
            }
            for a in agents
        ],
        "markdown": KimiDisplay.status_to_markdown(status),
        "short": KimiDisplay.short_status(status),
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def swarm_ui(port: int = 0) -> dict[str, Any]:
    """Launch the live web dashboard in your browser."""
    orch = _get_orch()
    actual_port = launch_persistent_dashboard(
        port=port, state_path=_state_path, open_browser=True
    )
    url = f"http://127.0.0.1:{actual_port}"
    return {
        "url": url,
        "port": actual_port,
        "markdown": f"🌐 **Dashboard opened:** [{url}]({url})\n\n> Live swarm status with real-time updates via Server-Sent Events.",
        "short": f"Dashboard at {url}",
    }


@mcp.tool()
def swarm_ui_stop() -> dict[str, Any]:
    """Stop the live web dashboard."""
    orch = _get_orch()
    stop_all_dashboards(state_path=orch._state_path)
    return {
        "status": "stopped",
        "markdown": "🔴 **Dashboard stopped.**",
        "short": "Dashboard stopped",
    }


@mcp.tool()
def swarm_verify_dashboard() -> dict[str, Any]:
    """Verify the web dashboard is updating correctly.

    Checks:
    1. Dashboard server is responding
    2. State file exists and is fresh (< 5 seconds)
    3. Iteration count matches expected
    4. All agents are reflected in state
    """
    import urllib.request
    orch = _get_orch()
    status = orch.get_status()

    # Try to hit the dashboard verify endpoint
    dashboard_ok = False
    freshness = {}
    try:
        meta_path = _state_path.parent / "kimi-swarm-dashboard.json"
        if meta_path.exists():
            with open(meta_path, "r") as f:
                meta = json.load(f)
            port = meta.get("port")
            if port:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/verify",
                    method="GET",
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        freshness = json.loads(resp.read().decode("utf-8"))
                        dashboard_ok = freshness.get("is_state_fresh", False)
    except Exception as e:
        freshness = {"error": str(e)}

    all_ok = dashboard_ok and status.is_active
    verif_result = {
        "dashboard_ok": dashboard_ok,
        "state_fresh": freshness.get("is_state_fresh", False),
        "agent_count_match": freshness.get("agent_count", 0) == len(status.agents),
        "iteration_count": freshness.get("iteration_count", 0),
        "swarm_active": status.is_active,
        "details": freshness,
    }

    from .models import VerificationResult
    orch._last_verification = VerificationResult(
        passed=all_ok,
        feedback="Dashboard verification complete",
        web_ui_ok=dashboard_ok,
        web_ui_details=json.dumps(freshness),
    )

    emoji = "✅" if all_ok else "❌"
    md = (
        f"{emoji} **Dashboard Verification**\n\n"
        f"- Dashboard responding: {'✅' if dashboard_ok else '❌'}\n"
        f"- State fresh: {'✅' if freshness.get('is_state_fresh') else '❌'}\n"
        f"- Agent count match: {'✅' if verif_result['agent_count_match'] else '❌'}\n"
        f"- Swarm active: {'✅' if status.is_active else '❌'}\n"
        f"- Iterations: {verif_result['iteration_count']}\n"
    )

    return {
        "passed": all_ok,
        "result": verif_result,
        "markdown": KimiDisplay.status_to_markdown(status) + "\n\n" + md,
        "short": f"Dashboard verify: {'PASS' if all_ok else 'FAIL'}",
        "todos": _status_to_todos(status),
    }


@mcp.tool()
def swarm_demo() -> dict[str, Any]:
    """Run a quick demo swarm and return the final status."""
    orch = SwarmOrchestrator(topology="hierarchical", max_agents=5, state_path=_state_path)
    orch.init_swarm()
    orch.set_dashboard_broadcast(lambda: broadcast_now(state_path=_state_path))

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

    _state_path.parent.mkdir(parents=True, exist_ok=True)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
