"""Tests for kimi_swarm."""

from unittest.mock import patch, MagicMock

import pytest

from kimi_swarm.models import AgentConfig, AgentPhase, SwarmTopology, ContextWindow, VerificationResult
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

    def test_verification_result_defaults(self):
        v = VerificationResult()
        assert v.passed is False
        assert v.feedback == ""
        assert v.iteration_number == 0

    def test_verification_result_to_dict(self):
        v = VerificationResult(passed=True, feedback="ok", iteration_number=2)
        d = v.to_dict()
        assert d["passed"] is True
        assert d["feedback"] == "ok"
        assert d["iteration_number"] == 2


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

    def test_entry_point_agent(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        assert orch.entry_point_agent_id == ""
        a1 = orch.spawn_agent(AgentConfig(type="architect", name="arch-1"))
        assert orch.entry_point_agent_id == a1.agent_id
        a2 = orch.spawn_agent(AgentConfig(type="coder", name="coder-1"))
        # Entry-point should stay as the first agent
        assert orch.entry_point_agent_id == a1.agent_id
        assert orch.get_entry_point_agent().name == "arch-1"

    def test_state_persists_entry_point_agent(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "state.json")
            orch = SwarmOrchestrator(state_path=state_path)
            orch.init_swarm()
            a1 = orch.spawn_agent(AgentConfig(type="architect", name="arch-1"))
            orch.save_state()

            orch2 = SwarmOrchestrator(state_path=state_path)
            assert orch2.load_state()
            assert orch2.entry_point_agent_id == a1.agent_id
            assert orch2.get_entry_point_agent().name == "arch-1"


class TestAgenticLoop:
    def test_execute_with_verification_no_verifier(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="loop-dev"))
        result = orch.execute_with_verification(agent.agent_id, "do something")
        assert result["status"] == "completed"
        assert result["iteration"] == 1

    def test_execute_with_verification_tracks_iterations(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        dev = orch.spawn_agent(AgentConfig(type="coder", name="dev"))
        verifier = orch.spawn_agent(AgentConfig(type="tester", name="verifier"))
        result = orch.execute_with_verification(
            dev.agent_id,
            "build feature",
            verifier_agent_id=verifier.agent_id,
            max_iterations=3,
        )
        # With default 0% failure rate, should pass on first iteration
        assert result["status"] == "completed"
        assert result["iteration"] == 1
        assert result["verification"]["passed"] is True

    def test_acknowledge_failure(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="failer"))
        orch.assign_task(agent.agent_id, "task")
        agent.task.attempt_count = 2
        agent.task.max_attempts = 3
        agent.task.verification_status = "failed"
        agent.task.verification_feedback = "bad output"

        result = orch.acknowledge_failure(agent.agent_id)
        assert result["status"] == "acknowledged"
        assert result["history"]["attempt_count"] == 2
        assert result["history"]["verification_status"] == "failed"
        assert agent.phase == AgentPhase.PLANNING
        assert "failure_acknowledged" in agent.metadata

    def test_reassign_with_feedback(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        from_agent = orch.spawn_agent(AgentConfig(type="coder", name="from"))
        to_agent = orch.spawn_agent(AgentConfig(type="coder", name="to"))
        orch.assign_task(from_agent.agent_id, "original task")
        from_agent.task.attempt_count = 1
        from_agent.task.verification_feedback = "fix this"
        from_agent.metadata["failure_acknowledged"] = {"attempt_count": 1}

        result = orch.reassign_with_feedback(
            from_agent.agent_id, to_agent.agent_id, "corrected task"
        )
        assert result["status"] == "reassigned"
        assert to_agent.task.description == "corrected task"
        assert to_agent.task.attempt_count == 1
        assert "fix this" in to_agent.task.result

    def test_web_ui_state_check(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        assert orch._verify_web_ui_state() is True  # state file was just saved

    def test_total_iterations_tracked(self):
        orch = SwarmOrchestrator()
        orch.init_swarm()
        agent = orch.spawn_agent(AgentConfig(type="coder", name="iter"))
        assert orch.total_iterations == 0
        orch.execute_with_verification(agent.agent_id, "task")
        assert orch.total_iterations == 1


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


try:
    from kimi_swarm import mcp_server

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP / pydantic not available in this environment")
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

    def test_agent_execute_graceful_failure_routes_to_entry_point(self):
        """Verify agent_execute catches exceptions and returns guidance to route to entry-point agent."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038):
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            result = mcp_server.agent_spawn(agent_type="architect", name="coord", model="sonnet")
            ep_id = result["agent_id"]
            assert ep_id == mcp_server._orch.entry_point_agent_id

            # Execute on a non-existent agent — should NOT raise
            result = mcp_server.agent_execute(agent_id="no-such-agent", prompt="do something")
            assert result["status"] == "failed"
            assert "Do NOT take over this task yourself" in result["markdown"]
            assert ep_id in result["markdown"]
            assert "agent_execute" in result["markdown"]

    def test_agent_execute_failure_includes_entry_point_guidance(self):
        """Verify agent_execute failure response tells Kimi to route to entry-point agent."""
        from kimi_swarm import mcp_server
        from kimi_swarm.orchestrator import SwarmOrchestrator

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038):
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            mcp_server.agent_spawn(agent_type="coder", name="worker", model="haiku")

            # Force a failure by patching execute_task to return failed status
            with patch.object(SwarmOrchestrator, "execute_task", return_value={"status": "failed", "result": "bad output", "tokens": {}}):
                result = mcp_server.agent_execute(agent_id="worker", prompt="task")
                assert result["status"] == "failed"
                assert "Do NOT take over this task yourself" in result["markdown"]
                assert "entry-point agent" in result["markdown"]


class TestBrowserDeduplication:
    def test_should_open_browser_when_no_lock(self):
        from kimi_swarm.web_dashboard import _should_open_browser, _browser_lock_path
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = os.path.join(tmpdir, "browser.lock")
            assert _should_open_browser(lock) is True

    def test_should_not_open_browser_within_cooldown(self):
        from kimi_swarm.web_dashboard import _should_open_browser, _mark_browser_opened
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = os.path.join(tmpdir, "browser.lock")
            _mark_browser_opened(lock)
            assert _should_open_browser(lock, cooldown=30) is False

    def test_should_open_browser_after_cooldown(self):
        from kimi_swarm.web_dashboard import _should_open_browser, _mark_browser_opened
        import tempfile, os, time
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = os.path.join(tmpdir, "browser.lock")
            _mark_browser_opened(lock)
            assert _should_open_browser(lock, cooldown=0) is True

    def test_stop_all_dashboards_clears_browser_lock(self):
        from kimi_swarm.web_dashboard import _mark_browser_opened, _should_open_browser, stop_all_dashboards
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = os.path.join(tmpdir, "browser.lock")
            _mark_browser_opened(lock)
            assert _should_open_browser(lock) is False
            stop_all_dashboards(lock)
            assert _should_open_browser(lock) is True


class TestAgenticLoopMCP:
    def test_agent_execute_with_verification_mcp(self):
        """Verify agent_execute_with_verification MCP tool works end-to-end."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038):
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            mcp_server.agent_spawn(agent_type="coder", name="dev", model="sonnet")
            mcp_server.agent_spawn(agent_type="tester", name="vfy", model="haiku")

            result = mcp_server.agent_execute_with_verification(
                agent_id="dev",
                prompt="build auth",
                verifier_agent_id="vfy",
                max_iterations=2,
            )
            assert result["status"] == "completed"
            assert result["iteration"] == 1
            assert result["needs_retry"] is False
            assert "Agentic Loop Complete" in result["markdown"]

    def test_agent_acknowledge_failure_mcp(self):
        """Verify agent_acknowledge_failure MCP tool works."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038):
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            mcp_server.agent_spawn(agent_type="architect", name="coord", model="sonnet")

            result = mcp_server.agent_acknowledge_failure(agent_id="coord")
            assert result["status"] == "acknowledged"
            assert "Failure Acknowledged" in result["markdown"]

    def test_agent_reassign_with_feedback_mcp(self):
        """Verify agent_reassign_with_feedback MCP tool works."""
        from kimi_swarm import mcp_server

        with patch.object(mcp_server, "launch_persistent_dashboard", return_value=64038):
            mcp_server._orch = None
            if mcp_server._state_path.exists():
                mcp_server._state_path.unlink()

            mcp_server.swarm_init(topology="hierarchical", max_agents=3)
            mcp_server.agent_spawn(agent_type="coder", name="from", model="sonnet")
            mcp_server.agent_spawn(agent_type="coder", name="to", model="haiku")
            mcp_server.agent_assign(agent_id="from", task_description="old task")

            result = mcp_server.agent_reassign_with_feedback(
                from_agent_id="from",
                to_agent_id="to",
                corrected_prompt="fixed task",
            )
            assert result["status"] == "reassigned"
            assert "Task Reassigned" in result["markdown"]
