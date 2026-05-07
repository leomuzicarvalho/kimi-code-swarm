"""Tests for kimi_swarm."""

from unittest.mock import patch, MagicMock

import pytest

from kimi_swarm.models import AgentConfig, AgentPhase, SwarmTopology, ContextWindow
from kimi_swarm.orchestrator import SwarmOrchestrator
from kimi_swarm.display import KimiDisplay
from kimi_swarm import model_mapping


class TestModels:
    def test_context_window_calculation(self):
        ctx = ContextWindow(used_tokens=8000, max_tokens=32000)
        assert ctx.usage_percent == 25.0

    def test_context_window_update(self):
        ctx = ContextWindow(max_tokens=32000)
        ctx.update(16000)
        assert ctx.used_tokens == 16000
        assert ctx.usage_percent == 50.0


class TestOrchestrator:
    def test_init_swarm(self):
        orch = SwarmOrchestrator(topology="mesh", max_agents=3)
        status = orch.init_swarm()
        assert status.is_active
        assert status.topology == SwarmTopology.MESH
        assert status.max_agents == 3
        assert status.active_agents == 0

    def test_spawn_agent(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        cfg = AgentConfig(type="coder", name="test-agent", model="haiku")
        agent = orch.spawn_agent(cfg)
        assert agent.name == "test-agent"
        assert agent.agent_type == "coder"
        assert agent.model == "haiku"
        assert agent.resolved_model == "moonshot-v1-8k"
        assert agent.phase == AgentPhase.IDLE
        assert agent.context.max_tokens == 8192  # haiku → moonshot-v1-8k mapping

    def test_spawn_agent_sonnet_maps_to_k2_6(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="s1", model="sonnet"))
        assert agent.resolved_model == "kimi-k2.6"
        assert agent.context.max_tokens == 256000

    def test_spawn_agent_opus_maps_to_k2_6(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="o1", model="opus"))
        assert agent.resolved_model == "kimi-k2.6"
        assert agent.context.max_tokens == 256000

    def test_max_agents_limit(self):
        orch = SwarmOrchestrator(max_agents=1)
        orch.init_swarm()
        orch.spawn_agent(AgentConfig(type="coder", name="a1"))
        with pytest.raises(RuntimeError, match="Max agents"):
            orch.spawn_agent(AgentConfig(type="coder", name="a2"))

    def test_assign_and_execute_task(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="executor"))
        task = orch.assign_task(agent.agent_id, "Write a hello world function")
        assert task.description == "Write a hello world function"
        assert agent.phase == AgentPhase.PLANNING

        result = orch.execute_task(agent.agent_id, "Write a hello world function")
        assert result["status"] == "completed"
        assert agent.tokens.total_tokens > 0
        assert agent.task.status == "completed"
        assert agent.task.progress_percent == 100.0
        assert agent.phase == AgentPhase.COMPLETED

    def test_progress_update(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="p1"))
        orch.assign_task(agent.agent_id, "long task")
        orch.update_agent_progress(agent.agent_id, 42.5)
        assert agent.task.progress_percent == 42.5

    def test_terminate_agent(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="t1"))
        orch.terminate_agent(agent.agent_id)
        assert agent.phase == AgentPhase.TERMINATED

    def test_shutdown(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        orch.spawn_agent(AgentConfig(type="coder", name="s1"))
        status = orch.shutdown()
        assert not status.is_active
        assert all(a.phase == AgentPhase.TERMINATED for a in status.agents)

    def test_context_tracking(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="ctx"))
        orch.execute_task(agent.agent_id, "some prompt here with words")
        assert agent.context.used_tokens > 0
        assert agent.context.usage_percent > 0

    def test_main_context_tracking(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="main-ctx"))
        orch.execute_task(agent.agent_id, "task one two three")
        status = orch.get_status()
        assert status.main_context.used_tokens > 0

    def test_get_status_counts(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        a1 = orch.spawn_agent(AgentConfig(type="coder", name="a1"))
        a2 = orch.spawn_agent(AgentConfig(type="tester", name="a2"))
        orch.assign_task(a1.agent_id, "task1")
        orch.assign_task(a2.agent_id, "task2")
        orch.execute_task(a1.agent_id, "task1")
        orch.terminate_agent(a2.agent_id)

        status = orch.get_status()
        assert status.active_agents == 1  # a1 completed, a2 terminated
        assert status.completed_tasks == 1
        assert status.total_tasks == 2


class TestDisplay:
    def test_markdown_output(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        orch.spawn_agent(AgentConfig(type="coder", name="disp", model="sonnet"))
        status = orch.get_status()
        md = KimiDisplay.status_to_markdown(status)
        assert "Swarm Status" in md
        assert "disp" in md
        assert "sonnet" in md
        assert "Main Agent Context" in md

    def test_short_status(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        orch.spawn_agent(AgentConfig(type="coder", name="short"))
        status = orch.get_status()
        short = KimiDisplay.short_status(status)
        assert "short" in short
        assert "idl" in short  # truncated to 3 chars

    def test_progress_bar(self):
        bar = KimiDisplay._progress_bar(50)
        assert "50%" in bar
        assert "█" in bar

    def test_phase_emoji(self):
        assert KimiDisplay._phase_emoji(AgentPhase.EXECUTING) == "⚡"
        assert KimiDisplay._phase_emoji(AgentPhase.COMPLETED) == "✅"


class TestModelMappings:
    def test_resolve_kimi_model(self):
        assert model_mapping.resolve_kimi_model("haiku") == "moonshot-v1-8k"
        assert model_mapping.resolve_kimi_model("sonnet") == "kimi-k2.6"
        assert model_mapping.resolve_kimi_model("opus") == "kimi-k2.6"
        assert model_mapping.resolve_kimi_model("inherit") == "kimi-k2.6"
        # Explicit Kimi names pass through
        assert model_mapping.resolve_kimi_model("kimi-k2.6") == "kimi-k2.6"
        assert model_mapping.resolve_kimi_model("moonshot-v1-32k") == "moonshot-v1-32k"

    def test_get_context_size(self):
        assert model_mapping.get_context_size("haiku") == 8192
        assert model_mapping.get_context_size("sonnet") == 256000
        assert model_mapping.get_context_size("opus") == 256000
        assert model_mapping.get_context_size("kimi-k2.6") == 256000
        assert model_mapping.get_context_size("unknown") == 32768

    def test_model_context_sizes_legacy(self):
        orch = SwarmOrchestrator()
        assert orch._model_to_context_size("haiku") == 8192
        assert orch._model_to_context_size("sonnet") == 256000
        assert orch._model_to_context_size("opus") == 256000
        assert orch._model_to_context_size("kimi-k2.6") == 256000
        assert orch._model_to_context_size("unknown") == 32768


class TestDashboardIntegration:
    def test_swarm_init_launches_dashboard(self):
        """Verify swarm_init auto-launches the live web dashboard."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038) as mock_launch:
            # Ensure clean state
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            result = mcp_server.swarm_init(topology="hierarchical", max_agents=3)

            mock_launch.assert_called_once_with(
                port=0, state_path=mcp_server._state_path, open_browser=True
            )
            assert result["swarm_id"].startswith("swarm-")
            assert result["topology"] == "hierarchical"
            assert result["max_agents"] == 3

    def test_swarm_init_cleans_up_existing_swarm(self):
        """Verify swarm_init shuts down any existing swarm before creating a new one."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038):
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            # First init
            result1 = mcp_server.swarm_init(topology="mesh", max_agents=2)
            swarm_id_1 = result1["swarm_id"]

            # Second init should create a new swarm (clean up old one)
            result2 = mcp_server.swarm_init(topology="hierarchical", max_agents=5)
            swarm_id_2 = result2["swarm_id"]

            assert swarm_id_1 != swarm_id_2
            assert result2["topology"] == "hierarchical"
            assert result2["max_agents"] == 5

    def test_swarm_ui_tool_launches_dashboard(self):
        """Verify swarm_ui MCP tool launches the dashboard and returns the URL."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=8080) as mock_launch:
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            result = mcp_server.swarm_ui(port=8080)

            assert result["port"] == 8080
            assert result["url"] == "http://127.0.0.1:8080"
            assert "Dashboard opened" in result["markdown"]
            mock_launch.assert_called_with(
                port=8080, state_path=mcp_server._state_path, open_browser=True
            )

    def test_swarm_ui_stop_tool_stops_dashboard(self):
        """Verify swarm_ui_stop MCP tool stops the dashboard."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "stop_persistent_dashboard") as mock_stop:
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            result = mcp_server.swarm_ui_stop()

            assert result["status"] == "stopped"
            assert "Dashboard stopped" in result["markdown"]
            mock_stop.assert_called_once_with(state_path=mcp_server._state_path)
