"""Display formatters for Kimi's chat window and terminal."""

from __future__ import annotations

from dataclasses import asdict

from .models import AgentPhase, AgentStatus, SwarmStatus


class KimiDisplay:
    """Formats swarm status for display in Kimi's chat window."""

    @staticmethod
    def status_to_markdown(status: SwarmStatus) -> str:
        """Convert swarm status to a markdown table for Kimi's window."""
        lines: list[str] = []
        lines.append("## 🐝 Swarm Status")
        lines.append("")
        lines.append(f"**Swarm ID:** `{status.swarm_id}`  |  **Topology:** `{status.topology.value}`  |  **Active:** {status.active_agents}/{status.max_agents}")
        lines.append("")
        lines.append(f"📊 **Overall Progress:** {status.overall_progress:.1f}%  |  **Tasks:** {status.completed_tasks}/{status.total_tasks} completed")
        lines.append("")

        # Entry-point agent
        if status.entry_point_agent_id:
            ep_agent = next((a for a in status.agents if a.agent_id == status.entry_point_agent_id), None)
            if ep_agent:
                lines.append(f"🎯 **Entry-point agent:** `{ep_agent.name}` (`{ep_agent.agent_id}`) — use this agent to coordinate and route failures.")
                lines.append("")

        # Main agent context window
        main = status.main_context
        lines.append("### 🧠 Main Agent Context")
        lines.append(f"- **Used:** {main.used_tokens:,} / {main.max_tokens:,} tokens ({main.usage_percent:.1f}%)")
        lines.append(f"- **Available:** {main.max_tokens - main.used_tokens:,} tokens")
        lines.append("")

        if not status.agents:
            lines.append("*No agents spawned yet.*")
            return "\n".join(lines)

        # Agent table
        lines.append("### 🤖 Agents")
        lines.append("")
        lines.append("| Agent | Type | Model | Phase | Progress | Context | Prompt / Comp | Msg | Uptime | Task |")
        lines.append("|-------|------|-------|-------|----------|---------|-------------|-----|--------|------|")

        for agent in status.agents:
            progress_bar = KimiDisplay._progress_bar(agent.task.progress_percent if agent.task else 0)
            phase_emoji = KimiDisplay._phase_emoji(agent.phase)
            ctx = agent.context
            main_ctx = status.main_context

            # Context comparison
            agent_ctx_str = f"{ctx.used_tokens:,} / {ctx.max_tokens:,} ({ctx.usage_percent:.1f}%)"
            vs_main = f"{ctx.used_tokens / max(main_ctx.used_tokens, 1):.1f}x" if main_ctx.used_tokens > 0 else "N/A"

            tokens_str = f"{agent.tokens.prompt_tokens:,} / {agent.tokens.completion_tokens:,}"
            msg_count = agent.messages_count

            uptime_sec = int(agent.uptime_seconds)
            if uptime_sec < 60:
                uptime_str = f"{uptime_sec}s"
            elif uptime_sec < 3600:
                uptime_str = f"{uptime_sec // 60}m {uptime_sec % 60}s"
            else:
                uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"

            task_desc = agent.task.description if agent.task else ""
            if len(task_desc) > 30:
                task_desc = task_desc[:27] + "..."

            model_display = f"`{agent.model}` → `{agent.resolved_model}`" if agent.resolved_model and agent.resolved_model != agent.model else f"`{agent.model}`"
            lines.append(
                f"| {phase_emoji} **{agent.name}** | {agent.agent_type} | {model_display} | `{agent.phase.value}` | {progress_bar} | {agent_ctx_str} | {tokens_str} | {msg_count} | {uptime_str} | {task_desc} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**Legend:**")
        lines.append("- 🆕 idle | ⏳ planning | ⚡ executing | 👀 reviewing | ⏸️ waiting | ✅ completed | ❌ failed | 🛑 terminated")

        return "\n".join(lines)

    @staticmethod
    def status_to_rich(status: SwarmStatus) -> str:
        """Format for rich terminal output."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.progress import BarColumn, Progress, TextColumn
            from rich.panel import Panel
            from rich import box
        except ImportError:
            return KimiDisplay.status_to_markdown(status)

        console = Console(force_terminal=True, color_system="auto")
        with console.capture() as capture:
            console.print(Panel.fit(
                f"[bold cyan]Swarm {status.swarm_id}[/]  |  Topology: [yellow]{status.topology.value}[/]  |  Agents: [green]{status.active_agents}[/]/[green]{status.max_agents}[/]",
                title="🐝 Swarm Status",
                border_style="cyan",
            ))

            # Main context
            main = status.main_context
            console.print(f"\n[bold]Main Agent:[/] {main.used_tokens:,} / {main.max_tokens:,} tokens ({main.usage_percent:.1f}%)")

            if status.agents:
                table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
                table.add_column("Agent", style="cyan")
                table.add_column("Type")
                table.add_column("Kimi Model", style="dim")
                table.add_column("Phase", style="yellow")
                table.add_column("Progress")
                table.add_column("Agent Context", justify="right")
                table.add_column("vs Main", justify="right")
                table.add_column("Tokens", justify="right")

                for agent in status.agents:
                    ctx = agent.context
                    main_ctx = status.main_context
                    vs_main = f"{ctx.used_tokens / max(main_ctx.used_tokens, 1):.1f}x" if main_ctx.used_tokens > 0 else "N/A"
                    progress = f"{agent.task.progress_percent:.0f}%" if agent.task else "-"
                    model_label = f"{agent.model}→{agent.resolved_model}" if agent.resolved_model and agent.resolved_model != agent.model else agent.model
                    table.add_row(
                        agent.name,
                        agent.agent_type,
                        model_label,
                        agent.phase.value,
                        progress,
                        f"{ctx.usage_percent:.1f}%",
                        vs_main,
                        f"{agent.tokens.total_tokens:,}",
                    )
                console.print(table)
            else:
                console.print("[dim]No agents spawned yet.[/]")

        return capture.get()

    @staticmethod
    def _progress_bar(percent: float, width: int = 10) -> str:
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {percent:.0f}%"

    @staticmethod
    def _phase_emoji(phase: AgentPhase) -> str:
        mapping = {
            AgentPhase.IDLE: "🆕",
            AgentPhase.SPAWNING: "🐣",
            AgentPhase.PLANNING: "⏳",
            AgentPhase.EXECUTING: "⚡",
            AgentPhase.REVIEWING: "👀",
            AgentPhase.WAITING: "⏸️",
            AgentPhase.COMPLETED: "✅",
            AgentPhase.FAILED: "❌",
            AgentPhase.TERMINATED: "🛑",
        }
        return mapping.get(phase, "❓")

    @staticmethod
    def short_status(status: SwarmStatus) -> str:
        """One-line status summary."""
        agents_str = ", ".join(
            f"{a.name}({a.phase.value[:3]})"
            for a in status.agents
        )
        return f"Swarm {status.swarm_id[:8]}: {status.active_agents}/{status.max_agents} agents | {status.overall_progress:.0f}% done | [{agents_str}]"
