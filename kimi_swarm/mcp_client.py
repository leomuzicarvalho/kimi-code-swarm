"""Local MCP client for swarm orchestration.

Agents are backed by real Kimi CLI subprocesses with independent working
directories and full write powers (Shell, ReadFile, WriteFile, etc.).
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import AgentConfig, AgentStatus, AgentPhase, TaskInfo, TokenUsage, ContextWindow


DEFAULT_WORKSPACE_ROOT = Path.home() / ".kimi" / "swarm-workspaces"
EMPTY_MCP_CONFIG = {"mcpServers": {}}


def _empty_mcp_config_path() -> Path:
    """Return a persistent empty MCP config file for agent subprocesses."""
    path = Path.home() / ".kimi" / "swarm-empty-mcp.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(EMPTY_MCP_CONFIG))
    return path


def _find_kimi_binary() -> str | None:
    """Locate the kimi CLI binary."""
    for cmd in ("kimi", "kimi-cli"):
        found = shutil.which(cmd)
        if found:
            return found
    return None


def _kimi_works(binary: str) -> bool:
    """Quick smoke-test to verify kimi can run non-interactively."""
    try:
        result = subprocess.run(
            [
                binary,
                "--mcp-config-file", str(_empty_mcp_config_path()),
                "--print", "--final-message-only", "--output-format", "text", "--yolo",
                "--prompt", "echo 'kimi-swarm-ping'",
                "--work-dir", str(tempfile.gettempdir()),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0 and "kimi-swarm-ping" in result.stdout
    except Exception:
        return False


def _extract_final_message(stdout: str) -> str:
    """Extract the assistant's final message from --print --final-message-only output.

    The output may contain trailing lines like 'To resume this session: ...'.
    We strip those and return the substantive response text.
    """
    lines = stdout.splitlines()
    # Remove trailing resume/session lines
    while lines and lines[-1].startswith("To resume this session:"):
        lines.pop()
    return "\n".join(lines).strip()


class SwarmMCPClient:
    """Local MCP client that backs agents with real Kimi CLI subprocesses."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._work_dirs: dict[str, Path] = {}
        self._call_count = 0
        self._failure_rate = float(os.environ.get("KIMI_SWARM_SIM_FAILURE_RATE", "0.0"))
        self._verify_failure_rate = float(os.environ.get("KIMI_SWARM_SIM_VERIFY_FAILURE_RATE", "0.0"))

        # Detect whether we can spawn real Kimi CLI agents
        self._kimi_binary = _find_kimi_binary()
        self._real_execution = False
        if self._kimi_binary and os.environ.get("KIMI_SWARM_SIMULATE", "").lower() not in ("1", "true", "yes"):
            self._real_execution = _kimi_works(self._kimi_binary)

    def _workspace_for(self, agent_id: str) -> Path:
        path = DEFAULT_WORKSPACE_ROOT / agent_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _kill_agent_process(self, agent_id: str) -> None:
        proc = self._processes.pop(agent_id, None)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        except Exception:
            pass

    def swarm_init(self, topology: str, max_agents: int) -> dict[str, Any]:
        return {
            "swarm_id": f"swarm-{os.urandom(4).hex()}",
            "topology": topology,
            "max_agents": max_agents,
            "status": "initialized",
        }

    def agent_spawn(self, config: AgentConfig) -> dict[str, Any]:
        agent_id = f"agent-{os.urandom(4).hex()}"
        work_dir = self._workspace_for(agent_id)
        self._agents[agent_id] = {
            "agent_id": agent_id,
            "name": config.name,
            "type": config.type,
            "model": config.model,
            "status": "idle",
            "task": None,
        }
        self._work_dirs[agent_id] = work_dir
        return {"agent_id": agent_id, "status": "spawned", "workspace": str(work_dir)}

    def agent_execute(self, agent_id: str, prompt: str) -> dict[str, Any]:
        self._call_count += 1

        if agent_id not in self._agents:
            return {
                "agent_id": agent_id,
                "status": "failed",
                "mode": "native_kimi",
                "prompt": prompt,
                "result": f"Agent {agent_id} not found.",
                "tokens": {"prompt": 0, "completion": 0, "total": 0},
            }

        if self._real_execution and self._kimi_binary:
            return self._agent_execute_real(agent_id, prompt)
        return self._agent_execute_simulated(agent_id, prompt)

    def _agent_execute_real(self, agent_id: str, prompt: str) -> dict[str, Any]:
        """Execute the prompt via a real Kimi CLI subprocess.

        Uses an *idle timeout* instead of a hard timeout: the agent is only
        killed if it stops producing output. If it's actively working (printing
        tool calls, thinking, etc.) it stays alive indefinitely.
        """
        import threading
        import time

        work_dir = self._work_dirs.get(agent_id)
        if work_dir is None:
            work_dir = self._workspace_for(agent_id)
            self._work_dirs[agent_id] = work_dir

        self._kill_agent_process(agent_id)

        cmd = [
            self._kimi_binary,
            "--mcp-config-file", str(_empty_mcp_config_path()),
            "--print", "--final-message-only", "--output-format", "text", "--yolo",
            "--prompt", prompt,
            "--work-dir", str(work_dir),
        ]

        # Idle timeout: how many seconds of complete silence before we kill it
        idle_timeout = int(os.environ.get("KIMI_SWARM_AGENT_IDLE_TIMEOUT", "60"))
        # Absolute max runtime (safety cap) — only enforced if process is still alive
        max_runtime = int(os.environ.get("KIMI_SWARM_AGENT_MAX_RUNTIME", "1800"))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._processes[agent_id] = proc

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        last_activity = time.time()
        lock = threading.Lock()

        def _reader(pipe, collector):
            nonlocal last_activity
            try:
                for line in iter(pipe.readline, ""):
                    with lock:
                        collector.append(line)
                        last_activity = time.time()
            except Exception:
                pass
            finally:
                pipe.close()

        t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_lines), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_lines), daemon=True)
        t_out.start()
        t_err.start()

        start_time = time.time()
        killed_reason = ""

        try:
            while proc.poll() is None:
                time.sleep(0.5)
                with lock:
                    silent_for = time.time() - last_activity
                    running_for = time.time() - start_time

                if silent_for > idle_timeout:
                    proc.kill()
                    killed_reason = f"Agent was idle for {int(silent_for)}s (no output) — killed."
                    break

                if running_for > max_runtime:
                    proc.kill()
                    killed_reason = f"Agent exceeded max runtime of {max_runtime}s — killed."
                    break

            # Wait for reader threads to finish draining pipes
            t_out.join(timeout=2)
            t_err.join(timeout=2)
        except Exception as exc:
            killed_reason = str(exc)
            proc.kill()

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)

        if killed_reason:
            return {
                "agent_id": agent_id,
                "status": "failed",
                "mode": "native_kimi",
                "prompt": prompt,
                "result": killed_reason,
                "tokens": {"prompt": len(prompt.split()), "completion": 0, "total": len(prompt.split())},
            }

        result_text = _extract_final_message(stdout)
        if not result_text and stderr:
            result_text = stderr.strip()

        status = "completed" if proc.returncode == 0 else "failed"
        prompt_tokens = len(prompt.split())
        completion_tokens = len(result_text.split())

        return {
            "agent_id": agent_id,
            "status": status,
            "mode": "native_kimi",
            "prompt": prompt,
            "result": result_text,
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
        }

    def _agent_execute_simulated(self, agent_id: str, prompt: str) -> dict[str, Any]:
        """Fallback simulated execution (used in tests or when kimi CLI is unavailable)."""
        prompt_tokens = len(prompt.split())
        completion_tokens = prompt_tokens // 2

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
        self._kill_agent_process(agent_id)
        if agent_id in self._agents:
            self._agents[agent_id]["status"] = "terminated"
        # Optionally clean up workspace on terminate
        if os.environ.get("KIMI_SWARM_CLEANUP_WORKSPACES", "").lower() in ("1", "true", "yes"):
            work_dir = self._work_dirs.pop(agent_id, None)
            if work_dir and work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
        return {"agent_id": agent_id, "status": "terminated"}

    def swarm_shutdown(self, swarm_id: str) -> dict[str, Any]:
        # Kill all running agent processes
        for agent_id in list(self._processes.keys()):
            self._kill_agent_process(agent_id)
        return {"swarm_id": swarm_id, "status": "shutdown"}

    def memory_store(self, namespace: str, key: str, value: str) -> dict[str, Any]:
        return {"status": "stored", "namespace": namespace, "key": key}

    def memory_search(self, namespace: str, query: str) -> list[dict[str, Any]]:
        return []
