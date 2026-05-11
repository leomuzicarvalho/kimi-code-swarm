"""CLI entry point for kimi-swarm."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Sequence

from . import __version__
from .models import AgentConfig, AgentPhase, SwarmTopology
from .orchestrator import SwarmOrchestrator, DEFAULT_STATE_PATH
from .display import KimiDisplay
from .web_dashboard import (
    start_dashboard,
    stop_dashboard,
    launch_persistent_dashboard,
    stop_persistent_dashboard,
    stop_all_dashboards,
)


# Global orchestrator instance for CLI session
_current_orchestrator: SwarmOrchestrator | None = None


def get_orchestrator(require_init: bool = True) -> SwarmOrchestrator:
    """Get or restore the current orchestrator from persisted state."""
    global _current_orchestrator
    if _current_orchestrator is None:
        # Try to restore from disk
        orch = SwarmOrchestrator()
        if orch.load_state():
            _current_orchestrator = orch
        elif require_init:
            print("Error: No swarm initialized. Run 'kimi-swarm init' first.", file=sys.stderr)
            sys.exit(1)
    return _current_orchestrator


def resolve_agent(orch: SwarmOrchestrator, agent_ref: str) -> str:
    """Resolve an agent reference (name or ID) to an agent ID."""
    # Try as ID first
    try:
        orch.get_agent(agent_ref)
        return agent_ref
    except KeyError:
        pass
    # Try as name
    for agent in orch.list_agents():
        if agent.name == agent_ref:
            return agent.agent_id
    print(f"Error: Agent '{agent_ref}' not found.", file=sys.stderr)
    sys.exit(1)


def _maybe_open_ui(orch: SwarmOrchestrator, ui: bool, port: int) -> None:
    """Launch the web dashboard if requested."""
    if not ui:
        return
    actual_port = launch_persistent_dashboard(
        port=port, state_path=orch._state_path, open_browser=True
    )
    print(f"🌐 Dashboard running at http://127.0.0.1:{actual_port}")


def auto_status(orch: SwarmOrchestrator, quiet: bool = False, use_markdown: bool = True) -> None:
    """Automatically print swarm status after a command."""
    if quiet:
        return
    status = orch.get_status()
    if use_markdown:
        print("\n" + KimiDisplay.status_to_markdown(status) + "\n")
    else:
        print("\n" + KimiDisplay.status_to_rich(status) + "\n")


def cmd_init(args: argparse.Namespace) -> int:
    global _current_orchestrator
    # If --force, clear existing state first
    if args.force:
        SwarmOrchestrator().clear_state()

    orch = SwarmOrchestrator(topology=args.topology, max_agents=args.max_agents)
    status = orch.init_swarm()
    _current_orchestrator = orch
    print(f"✅ Swarm initialized: {status.swarm_id}")
    print(f"   Topology: {status.topology.value} | Max agents: {status.max_agents}")
    _maybe_open_ui(orch, args.ui, args.port)
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_spawn(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    config = AgentConfig(
        type=args.type,
        name=args.name,
        model=args.model,
        domain=args.domain or "",
        task=args.task or "",
    )
    agent = orch.spawn_agent(config)
    resolved = agent.resolved_model if agent.resolved_model != agent.model else agent.model
    print(f"🤖 Agent spawned: {agent.name} ({agent.agent_id})")
    print(f"   Type: {agent.agent_type} | Model: {agent.model} → {resolved} | Phase: {agent.phase.value}")
    _maybe_open_ui(orch, args.ui, args.port)
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    status = orch.get_status()

    if args.json:
        data = {
            "swarm_id": status.swarm_id,
            "topology": status.topology.value,
            "active_agents": status.active_agents,
            "max_agents": status.max_agents,
            "overall_progress": status.overall_progress,
            "main_context": {
                "used_tokens": status.main_context.used_tokens,
                "max_tokens": status.main_context.max_tokens,
                "usage_percent": status.main_context.usage_percent,
            },
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "type": a.agent_type,
                    "model": a.model,
                    "phase": a.phase.value,
                    "progress": a.task.progress_percent if a.task else 0.0,
                    "context_used": a.context.used_tokens,
                    "context_max": a.context.max_tokens,
                    "tokens_total": a.tokens.total_tokens,
                }
                for a in status.agents
            ],
        }
        print(json.dumps(data, indent=2))
        return 0

    if args.kimi_display:
        print(KimiDisplay.status_to_markdown(status))
    else:
        print(KimiDisplay.status_to_rich(status))
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    agent_id = resolve_agent(orch, args.agent)
    agent = orch.get_agent(agent_id)
    print(f"⚡ Executing task on {agent.name}...")
    result = orch.execute_task(agent_id, args.task)
    print(f"   Status: {result.get('status')}")
    print(f"   Tokens used: {result.get('tokens', {}).get('total', 'N/A')}")
    if result.get('result'):
        print(f"   Result: {result['result'][:200]}")
    _maybe_open_ui(orch, args.ui, args.port)
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    agent_id = resolve_agent(orch, args.agent)
    agent = orch.get_agent(agent_id)
    task = orch.assign_task(agent_id, args.task)
    print(f"📝 Task assigned to {agent.name}: {task.task_id}")
    print(f"   Description: {task.description}")
    _maybe_open_ui(orch, args.ui, args.port)
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    agent_id = resolve_agent(orch, args.agent)
    agent = orch.get_agent(agent_id)
    orch.update_agent_progress(agent_id, args.percent)
    print(f"📊 Updated {agent.name} progress to {args.percent}%")
    _maybe_open_ui(orch, args.ui, args.port)
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_phase(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    agent_id = resolve_agent(orch, args.agent)
    agent = orch.get_agent(agent_id)
    orch.set_agent_phase(agent_id, args.phase)
    print(f"🔖 Set {agent.name} phase to {args.phase}")
    _maybe_open_ui(orch, args.ui, args.port)
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_terminate(args: argparse.Namespace) -> int:
    orch = get_orchestrator()
    agent_id = resolve_agent(orch, args.agent)
    agent = orch.get_agent(agent_id)
    orch.terminate_agent(agent_id)
    print(f"🛑 Agent {agent.name} terminated")
    auto_status(orch, quiet=args.quiet, use_markdown=not args.rich)
    return 0


def cmd_shutdown(args: argparse.Namespace) -> int:
    global _current_orchestrator
    orch = get_orchestrator()
    status = orch.shutdown()
    print(f"🔴 Swarm {status.swarm_id} shut down")
    if args.clear_state:
        orch.clear_state()
    stop_all_dashboards(state_path=orch._state_path)
    _current_orchestrator = None
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Continuously watch and display swarm status."""
    orch = get_orchestrator()
    interval = args.interval
    use_markdown = args.kimi_display

    try:
        while True:
            # Clear screen (ANSI escape sequence)
            print("\033[2J\033[H", end="")
            status = orch.get_status()
            if use_markdown:
                print(KimiDisplay.status_to_markdown(status))
            else:
                print(KimiDisplay.status_to_rich(status))
            print(f"\n⏱️  Refreshing every {interval}s (Ctrl+C to stop)")
            time.sleep(interval)
            # Reload state in case another process modified it
            orch.load_state()
    except KeyboardInterrupt:
        print("\n👋 Watch stopped.")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run a quick demo of the swarm."""
    global _current_orchestrator
    print("🚀 Running Kimi Swarm Demo...\n")

    orch = SwarmOrchestrator(topology="hierarchical", max_agents=5)
    status = orch.init_swarm()
    _current_orchestrator = orch
    _maybe_open_ui(orch, args.ui, args.port)
    print(KimiDisplay.status_to_markdown(status))
    print("\n")

    # Spawn agents
    configs = [
        AgentConfig(type="architect", name="architect-1", model="sonnet"),
        AgentConfig(type="coder", name="coder-1", model="sonnet"),
        AgentConfig(type="coder", name="coder-2", model="haiku"),
        AgentConfig(type="tester", name="tester-1", model="haiku"),
        AgentConfig(type="reviewer", name="reviewer-1", model="sonnet"),
    ]
    for cfg in configs:
        agent = orch.spawn_agent(cfg)
        print(f"Spawned {agent.name} ({agent.model}) -> {agent.agent_id}")

    print("\n" + KimiDisplay.status_to_markdown(orch.get_status()))
    print("\n")

    # Simulate some work
    tasks = [
        ("coder-1", "Implement user authentication module with OAuth2 support and JWT tokens"),
        ("coder-2", "Create database schema for users and sessions"),
        ("tester-1", "Write unit tests for the authentication module covering edge cases"),
        ("reviewer-1", "Review authentication implementation for security best practices"),
    ]

    for name, task in tasks:
        agent_id = [a.agent_id for a in orch.list_agents() if a.name == name][0]
        print(f"⚡ {name} executing: {task[:60]}...")
        orch.execute_task(agent_id, task)

    print("\n" + KimiDisplay.status_to_markdown(orch.get_status()))
    print("\n")

    # Update progress on one agent
    orch.update_agent_progress(agent_id, 75.0)
    print("\n📊 After progress update:\n")
    print(KimiDisplay.status_to_markdown(orch.get_status()))

    orch.shutdown()
    orch.clear_state()
    stop_dashboard()
    _current_orchestrator = None
    print("\n✅ Demo complete!")
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Open the web dashboard for the current swarm."""
    orch = get_orchestrator()
    actual_port = start_dashboard(
        port=args.port, state_path=orch._state_path, open_browser=True
    )
    print(f"🌐 Dashboard running at http://127.0.0.1:{actual_port}")
    print("Press Ctrl+C to stop the dashboard server.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped.")
        stop_dashboard()
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common flags shared across subcommands."""
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress auto-status display after command")
    parser.add_argument("--rich", action="store_true", help="Use rich terminal output instead of markdown")
    parser.add_argument("--ui", action="store_true", help="Open live web dashboard in browser")
    parser.add_argument("--port", type=int, default=0, help="Dashboard port (0 = auto-assign)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kimi-swarm",
        description="Swarm orchestration CLI for Kimi Code",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new swarm")
    p_init.add_argument("--topology", choices=["hierarchical", "mesh", "consensus"], default="hierarchical")
    p_init.add_argument("--max-agents", type=int, default=5)
    p_init.add_argument("--force", action="store_true", help="Force re-initialization (clear existing state)")
    _add_common_args(p_init)
    p_init.set_defaults(func=cmd_init)

    # spawn
    p_spawn = subparsers.add_parser("spawn", help="Spawn an agent")
    p_spawn.add_argument("--type", required=True, help="Agent type (coder, tester, etc.)")
    p_spawn.add_argument("--name", required=True, help="Agent name")
    p_spawn.add_argument("--model", default="inherit", help="Model to use")
    p_spawn.add_argument("--domain", default="", help="Specialization domain")
    p_spawn.add_argument("--task", default="", help="Initial task description")
    _add_common_args(p_spawn)
    p_spawn.set_defaults(func=cmd_spawn)

    # status
    p_status = subparsers.add_parser("status", help="Show swarm status")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_status.add_argument("--kimi-display", "--markdown", action="store_true", help="Format for Kimi window (markdown)")
    p_status.set_defaults(func=cmd_status)

    # assign
    p_assign = subparsers.add_parser("assign", help="Assign a task to an agent")
    p_assign.add_argument("--agent", required=True, help="Agent ID or name")
    p_assign.add_argument("--task", required=True, help="Task description")
    _add_common_args(p_assign)
    p_assign.set_defaults(func=cmd_assign)

    # execute
    p_exec = subparsers.add_parser("execute", help="Execute a task on an agent")
    p_exec.add_argument("--agent", required=True, help="Agent ID or name")
    p_exec.add_argument("--task", required=True, help="Task prompt")
    _add_common_args(p_exec)
    p_exec.set_defaults(func=cmd_execute)

    # progress
    p_prog = subparsers.add_parser("progress", help="Update agent progress")
    p_prog.add_argument("--agent", required=True, help="Agent ID or name")
    p_prog.add_argument("--percent", type=float, required=True, help="Progress 0-100")
    _add_common_args(p_prog)
    p_prog.set_defaults(func=cmd_progress)

    # phase
    p_phase = subparsers.add_parser("phase", help="Set agent phase")
    p_phase.add_argument("--agent", required=True, help="Agent ID or name")
    p_phase.add_argument("--phase", required=True, choices=[p.value for p in AgentPhase])
    _add_common_args(p_phase)
    p_phase.set_defaults(func=cmd_phase)

    # terminate
    p_term = subparsers.add_parser("terminate", help="Terminate an agent")
    p_term.add_argument("--agent", required=True, help="Agent ID or name")
    _add_common_args(p_term)
    p_term.set_defaults(func=cmd_terminate)

    # shutdown
    p_shutdown = subparsers.add_parser("shutdown", help="Shutdown the swarm")
    p_shutdown.add_argument("--clear-state", action="store_true", help="Remove persisted state file after shutdown")
    _add_common_args(p_shutdown)
    p_shutdown.set_defaults(func=cmd_shutdown)

    # watch
    p_watch = subparsers.add_parser("watch", help="Continuously watch swarm status")
    p_watch.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds")
    p_watch.add_argument("--kimi-display", "--markdown", action="store_true", help="Use markdown format")
    p_watch.set_defaults(func=cmd_watch)

    # ui
    p_ui = subparsers.add_parser("ui", help="Open the live web dashboard")
    p_ui.add_argument("--port", type=int, default=0, help="Dashboard port (0 = auto-assign)")
    p_ui.set_defaults(func=cmd_ui)

    # demo
    p_demo = subparsers.add_parser("demo", help="Run a demo swarm")
    p_demo.add_argument("--ui", action="store_true", help="Open live web dashboard in browser")
    p_demo.add_argument("--port", type=int, default=0, help="Dashboard port (0 = auto-assign)")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(args: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    return parsed.func(parsed)


if __name__ == "__main__":
    sys.exit(main())
