#!/usr/bin/env python3
"""
Dashboard Verification Script

Deploys a swarm, starts the web dashboard, and uses Playwright to verify
that the UI updates live with agent tasks, progress, phases, tokens, and context.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

# Add project root to path so we can import kimi_swarm
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from kimi_swarm.orchestrator import SwarmOrchestrator
from kimi_swarm.models import AgentConfig, AgentPhase
from kimi_swarm.web_dashboard import start_dashboard, stop_dashboard


class DashboardVerifier:
    """Orchestrates swarm deployment and Playwright-based UI verification."""

    def __init__(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="kimi-swarm-verify-"))
        self.state_path = self.temp_dir / "swarm-state.json"
        self.screenshots_dir = self.temp_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)
        self.orchestrator: SwarmOrchestrator | None = None
        self.dashboard_port: int = 0
        self.results: list[dict] = []

    def log(self, msg: str) -> None:
        print(f"[VERIFY] {msg}")

    def deploy_swarm(self) -> None:
        """Initialize swarm and spawn agents with tasks."""
        self.log("Deploying swarm...")
        self.orchestrator = SwarmOrchestrator(
            topology="hierarchical",
            max_agents=5,
            state_path=self.state_path,
        )
        self.orchestrator.init_swarm()
        self.log(f"Swarm initialized: {self.orchestrator.swarm_id}")

        configs = [
            AgentConfig(type="architect", name="architect-1", model="sonnet"),
            AgentConfig(type="coder", name="coder-1", model="sonnet"),
            AgentConfig(type="tester", name="tester-1", model="haiku"),
            AgentConfig(type="reviewer", name="reviewer-1", model="sonnet"),
        ]
        for cfg in configs:
            agent = self.orchestrator.spawn_agent(cfg)
            self.log(f"Spawned {agent.name} ({agent.agent_id}) -> phase={agent.phase.value}")

        self.orchestrator.assign_task(
            self._agent_id_by_name("coder-1"),
            "Implement OAuth2 authentication module with JWT tokens",
        )
        self.orchestrator.assign_task(
            self._agent_id_by_name("tester-1"),
            "Write unit tests for auth module covering edge cases",
        )
        self.orchestrator.assign_task(
            self._agent_id_by_name("reviewer-1"),
            "Review authentication implementation for security best practices",
        )
        self.log("Tasks assigned.")

    def _agent_id_by_name(self, name: str) -> str:
        for a in self.orchestrator.list_agents():  # type: ignore[union-attr]
            if a.name == name:
                return a.agent_id
        raise KeyError(name)

    def start_dashboard(self) -> int:
        """Start the dashboard server."""
        self.log("Starting dashboard server...")
        port = start_dashboard(
            port=0,
            state_path=self.state_path,
            open_browser=False,
        )
        self.dashboard_port = port
        self.log(f"Dashboard running at http://127.0.0.1:{port}")
        time.sleep(1.0)
        return port

    def _screenshot(self, page, name: str) -> Path:
        path = self.screenshots_dir / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        self.log(f"Screenshot saved: {path}")
        return path

    def _assert_condition(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append({"name": name, "passed": passed, "detail": detail})
        status = "PASS" if passed else "FAIL"
        self.log(f"[{status}] {name} {detail}")

    def verify_with_playwright(self) -> None:
        """Run Playwright to verify live dashboard updates."""
        if self.dashboard_port == 0:
            raise RuntimeError("Dashboard not started")

        url = f"http://127.0.0.1:{self.dashboard_port}"

        # Health-check before launching browser
        for i in range(10):
            try:
                with urllib.request.urlopen(f"{url}/api/status", timeout=2) as resp:
                    _ = resp.read()
                self.log("Dashboard health check passed.")
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError("Dashboard did not respond to health check")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            # ------------------------------------------------------------------
            # 1. Initial load
            # ------------------------------------------------------------------
            self.log("Navigating to dashboard...")
            page.goto(url, timeout=15000)
            page.wait_for_selector("#connText", state="visible", timeout=10000)

            # Wait for SSE to show Live
            try:
                page.wait_for_function(
                    "() => document.getElementById('connText').textContent === 'Live'",
                    timeout=8000,
                )
                self._assert_condition("SSE connection established", True)
            except Exception as exc:
                self._assert_condition("SSE connection established", False, str(exc))

            self._screenshot(page, "01_initial_load")

            # ------------------------------------------------------------------
            # 2. Swarm overview stats
            # ------------------------------------------------------------------
            try:
                active_agents = page.locator("#activeAgents").inner_text()
                max_agents = page.locator("#maxAgents").inner_text()
                self._assert_condition(
                    "Swarm overview renders",
                    active_agents == "4" and max_agents == "5",
                    f"active={active_agents}, max={max_agents}",
                )
            except Exception as exc:
                self._assert_condition("Swarm overview renders", False, str(exc))

            # ------------------------------------------------------------------
            # 3. Agent cards count
            # ------------------------------------------------------------------
            try:
                count = page.locator(".agent-card").count()
                self._assert_condition(
                    "Agent cards displayed",
                    count == 4,
                    f"expected 4, got {count}",
                )
            except Exception as exc:
                self._assert_condition("Agent cards displayed", False, str(exc))

            # Agent names visible
            for name in ["architect-1", "coder-1", "tester-1", "reviewer-1"]:
                try:
                    text = page.inner_text("body")
                    self._assert_condition(f"Agent '{name}' visible", name in text)
                except Exception as exc:
                    self._assert_condition(f"Agent '{name}' visible", False, str(exc))

            # ------------------------------------------------------------------
            # 4. Task descriptions
            # ------------------------------------------------------------------
            try:
                body = page.inner_text("body")
                has_task = "OAuth2" in body or "unit tests" in body or "Review" in body
                self._assert_condition("Task descriptions rendered", has_task)
            except Exception as exc:
                self._assert_condition("Task descriptions rendered", False, str(exc))

            # ------------------------------------------------------------------
            # 5. Live updates: progress & phase
            # ------------------------------------------------------------------
            self.log("Triggering live state changes...")
            orch = self.orchestrator
            coder_id = self._agent_id_by_name("coder-1")
            orch.update_agent_progress(coder_id, 42.0)
            orch.set_agent_phase(coder_id, AgentPhase.EXECUTING)

            tester_id = self._agent_id_by_name("tester-1")
            orch.update_agent_progress(tester_id, 75.0)
            orch.set_agent_phase(tester_id, AgentPhase.PLANNING)

            time.sleep(2.0)
            self._screenshot(page, "02_after_live_updates")

            # Read updated DOM via JS for robustness
            try:
                agents_data = page.evaluate("""
                    () => {
                        const cards = Array.from(document.querySelectorAll('.agent-card'));
                        return cards.map(card => {
                            const name = card.querySelector('.agent-name')?.textContent || '';
                            const phase = card.querySelector('.phase-badge')?.textContent || '';
                            const prog = card.querySelector('.prog-pct')?.textContent || '';
                            return { name, phase, prog };
                        });
                    }
                """)
                coder = next((a for a in agents_data if a["name"] == "coder-1"), None)
                tester = next((a for a in agents_data if a["name"] == "tester-1"), None)

                coder_ok = coder is not None and coder["phase"] == "executing" and "42" in coder["prog"]
                tester_ok = tester is not None and tester["phase"] == "planning" and "75" in tester["prog"]
                self._assert_condition(
                    "coder-1 progress & phase updated live",
                    coder_ok,
                    str(coder) if coder else "not found",
                )
                self._assert_condition(
                    "tester-1 progress & phase updated live",
                    tester_ok,
                    str(tester) if tester else "not found",
                )
            except Exception as exc:
                self._assert_condition("Live updates reflected in DOM", False, str(exc))

            # ------------------------------------------------------------------
            # 6. Execute task → token & context stats
            # ------------------------------------------------------------------
            self.log("Executing task to generate token stats...")
            orch.execute_task(coder_id, "Implement login endpoint with rate limiting")
            time.sleep(1.5)
            self._screenshot(page, "03_after_task_execution")

            try:
                agents_data = page.evaluate("""
                    () => {
                        const cards = Array.from(document.querySelectorAll('.agent-card'));
                        return cards.map(card => {
                            const name = card.querySelector('.agent-name')?.textContent || '';
                            const tok_total = card.querySelector('.tok-total')?.textContent || '0';
                            const ctx_used = card.querySelector('.ctx-used')?.textContent || '0';
                            return { name, tok_total, ctx_used };
                        });
                    }
                """)
                coder = next((a for a in agents_data if a["name"] == "coder-1"), None)
                if coder:
                    tok = int(coder["tok_total"].replace(",", ""))
                    ctx = int(coder["ctx_used"].replace(",", ""))
                    self._assert_condition("Token stats updated after execution", tok > 0, f"tokens={tok}")
                    self._assert_condition("Context usage updated after execution", ctx > 0, f"ctx={ctx}")
                else:
                    self._assert_condition("Token stats updated after execution", False, "coder-1 not found")
                    self._assert_condition("Context usage updated after execution", False, "coder-1 not found")
            except Exception as exc:
                self._assert_condition("Token stats updated after execution", False, str(exc))
                self._assert_condition("Context usage updated after execution", False, str(exc))

            # ------------------------------------------------------------------
            # 7. Overall progress ring
            # ------------------------------------------------------------------
            try:
                overall = page.locator("#overallPercent").inner_text()
                self._assert_condition("Overall progress ring displays value", "%" in overall, f"overall={overall}")
            except Exception as exc:
                self._assert_condition("Overall progress ring displays value", False, str(exc))

            # ------------------------------------------------------------------
            # 8. Main context bar
            # ------------------------------------------------------------------
            try:
                main_label = page.locator("#mainCtxLabel").inner_text()
                self._assert_condition(
                    "Main context bar shows token data",
                    "/" in main_label and "%" in main_label,
                    f"label={main_label}",
                )
            except Exception as exc:
                self._assert_condition("Main context bar shows token data", False, str(exc))

            # ------------------------------------------------------------------
            # 9. Offline overlay hidden
            # ------------------------------------------------------------------
            try:
                classes = page.locator("#offlineOverlay").evaluate("el => el.className")
                self._assert_condition("Offline overlay hidden for active swarm", "show" not in classes, f"classes={classes}")
            except Exception as exc:
                self._assert_condition("Offline overlay hidden for active swarm", False, str(exc))

            # ------------------------------------------------------------------
            # 10. Terminate agent & verify UI
            # ------------------------------------------------------------------
            self.log("Terminating reviewer-1...")
            reviewer_id = self._agent_id_by_name("reviewer-1")
            orch.terminate_agent(reviewer_id)
            time.sleep(1.5)
            self._screenshot(page, "04_after_termination")

            try:
                agents_data = page.evaluate("""
                    () => {
                        const cards = Array.from(document.querySelectorAll('.agent-card'));
                        return cards.map(card => ({
                            name: card.querySelector('.agent-name')?.textContent || '',
                            phase: card.querySelector('.phase-badge')?.textContent || ''
                        }));
                    }
                """)
                reviewer = next((a for a in agents_data if a["name"] == "reviewer-1"), None)
                self._assert_condition(
                    "Terminated agent phase updated",
                    reviewer is not None and reviewer["phase"] == "terminated",
                    str(reviewer) if reviewer else "not found",
                )
            except Exception as exc:
                self._assert_condition("Terminated agent phase updated", False, str(exc))

            # ------------------------------------------------------------------
            # 11. API status endpoint (use urllib to avoid Playwright req timeout)
            # ------------------------------------------------------------------
            try:
                with urllib.request.urlopen(f"{url}/api/status", timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                self._assert_condition(
                    "API /api/status returns valid JSON",
                    "swarm_id" in data and "agents" in data,
                    f"keys={list(data.keys())}",
                )
            except Exception as exc:
                self._assert_condition("API /api/status returns valid JSON", False, str(exc))

            browser.close()

    def print_summary(self) -> int:
        """Print summary and return exit code."""
        print("\n" + "=" * 60)
        print("DASHBOARD VERIFICATION SUMMARY")
        print("=" * 60)
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        for r in self.results:
            icon = "✅" if r["passed"] else "❌"
            print(f"{icon} {r['name']}")
            if r["detail"]:
                print(f"   → {r['detail']}")
        print("-" * 60)
        print(f"Results: {passed}/{total} checks passed")
        print(f"Screenshots: {self.screenshots_dir}")
        print(f"Temp dir: {self.temp_dir}")
        print("=" * 60)
        return 0 if passed == total else 1

    def cleanup(self) -> None:
        """Shutdown swarm and stop dashboard."""
        self.log("Cleaning up...")
        if self.orchestrator:
            try:
                self.orchestrator.shutdown()
                self.orchestrator.clear_state()
            except Exception as exc:
                self.log(f"Shutdown error (non-fatal): {exc}")
        stop_dashboard()


def main() -> int:
    verifier = DashboardVerifier()
    try:
        verifier.deploy_swarm()
        verifier.start_dashboard()
        verifier.verify_with_playwright()
    finally:
        verifier.cleanup()
    return verifier.print_summary()


if __name__ == "__main__":
    sys.exit(main())
