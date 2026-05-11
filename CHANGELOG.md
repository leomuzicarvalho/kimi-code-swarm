# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- **Agentic Loop with Verification** — The swarm now supports a full execute-verify-retry cycle:
  - `SwarmOrchestrator.execute_with_verification(agent_id, prompt, verifier_agent_id, max_iterations=3)` runs a task and optionally verifies the result. If verification fails and iterations remain, it stores feedback, increments `attempt_count`, and returns a structured payload with `route_to_entry_point` and `needs_retry: true`.
  - `SwarmOrchestrator.acknowledge_failure(agent_id)` digests iteration history (attempt count, verification status, feedback) on the entry-point agent and stores it in `agent.metadata["failure_acknowledged"]`.
  - `SwarmOrchestrator.reassign_with_feedback(from_agent_id, to_agent_id, corrected_prompt)` routes a corrected task to a new agent, carrying forward the full iteration history and verification feedback.
  - New MCP tools: `agent_execute_with_verification`, `agent_acknowledge_failure`, `agent_reassign_with_feedback`.
  - `VerificationResult` dataclass tracks `passed`, `feedback`, `web_ui_ok`, `web_ui_details`, and `iteration_number`.
  - `TaskInfo` extended with `attempt_count`, `max_attempts`, `verification_status`, `verification_feedback`, and `last_iteration_at`.
  - `SwarmStatus` extended with `total_iterations` and `last_verification`.
  - Dashboard HTML shows an **iteration badge** (global loop counter), a **verification pill** per agent (passed/failed/pending), and **attempt count** (e.g., `Attempt: 2/3`).
  - `mcp_client.py` supports configurable simulation failure rates via `KIMI_SWARM_SIM_FAILURE_RATE` and `KIMI_SWARM_SIM_VERIFY_FAILURE_RATE` environment variables for testing the loop.
  - After **every loop iteration**, the dashboard receives an immediate SSE broadcast via `_broadcast_now()` and the state file is saved.

- **Dashboard Verification Endpoint** — `/api/verify` returns:
  - `is_state_fresh` — state file modified within last 5 seconds
  - `last_update_timestamp` — ISO timestamp of last state file write
  - `agent_count`, `iteration_count`, `swarm_id`, `is_active`
  - New MCP tool `swarm_verify_dashboard` queries this endpoint and reports dashboard health.

- **Browser Tab Deduplication** — Ensures only **one browser tab** is ever opened for swarm info:
  - `_browser_lock_path()` → `~/.kimi/kimi-swarm-browser.lock` tracks the last browser open time.
  - `_should_open_browser(cooldown=30)` returns `False` if a tab was opened within the last 30 seconds.
  - `_mark_browser_opened()` writes the current timestamp to the lock file.
  - `stop_all_dashboards()` clears the lock so a fresh init can open a new tab.
  - Both `start_dashboard()` and `launch_persistent_dashboard()` respect the cooldown before calling `webbrowser.open()`.

### Changed

- **`start_dashboard()` unified with persistent dashboard discovery** — Before starting a new in-process server, it now checks `find_running_dashboard()` first. If a persistent background dashboard is already running, it returns that port instead of spawning a duplicate. This prevents competing servers.
- **`swarm_ui` MCP tool now uses `launch_persistent_dashboard()`** instead of `start_dashboard()`. The dashboard survives MCP server restarts and goes through the same deduplication path as `swarm_init`.
- **`swarm_init()` stops all existing dashboards before launching** — Calls `stop_all_dashboards()` during reinit to kill stale persistent processes, stop in-process servers, and clear the browser lock. Guarantees a clean slate.
- **`swarm_ui_stop()` and CLI `cmd_shutdown()` use `stop_all_dashboards()`** for consistent cleanup of both server types.

### Fixed

- **`_check_state_freshness()` missing `datetime` import** — Added `from datetime import datetime` at the top of `web_dashboard.py` so the `/api/verify` endpoint can format timestamps correctly.
- **Verifier prompt detection in `mcp_client.py`** — Verification prompts now return `"PASSED: ..."` on success and `"FAILED: ..."` on failure so the agentic loop can parse them correctly.
- **`reassign_with_feedback()` now includes `verification_feedback`** in the new agent's `task.result` alongside the iteration history.

## [0.1.0] - 2025-05-XX

### Fixed

- **Swarm cycle dies on first agent failure** — When an `agent_execute` call failed (or threw an exception), Kimi would abandon the swarm and take over the task directly. The MCP tool now catches all exceptions and returns a structured failure response. Crucially, the response markdown includes explicit guidance: **"Do NOT take over this task yourself. Route this failure to the entry-point agent ... for coordination and reassignment."** This keeps the swarm cycle alive by giving Kimi a concrete next step inside the tool layer rather than falling back to direct execution.

### Added

- **Entry-point agent tracking** — The first agent spawned in a swarm is automatically designated as the *entry-point agent* (coordinator). Its ID is stored in `SwarmStatus.entry_point_agent_id` and persisted across sessions. The orchestrator exposes `get_entry_point_agent()` for lookups. The swarm status markdown now prominently displays `🎯 Entry-point agent: {name} ({id})` so Kimi always knows who to route failures to.

### Fixed

- **Apple Silicon architecture mismatch in MCP config** — On Apple Silicon Macs with universal Python binaries, the MCP server could fail intermittently with `mach-o file, but is an incompatible architecture`. This occurred when native extension packages (e.g., `pydantic-core`, `rpds-py`) were compiled for x86_64 (e.g., via Rosetta) but the MCP server spawned as arm64. `install.sh` now detects this situation and writes the MCP config with an `arch -arm64` wrapper (`"command": "arch", "args": ["-arm64", "python3", ...]`), ensuring deterministic arm64 execution regardless of parent process architecture. Updated README with manual configuration instructions for this scenario.

### Added

- **MCP Server Setup documentation in README** — Added a dedicated section explaining how to manually configure `~/.kimi/mcp.json`, with a clear warning to use the **absolute path** to the Python interpreter. This prevents the common pitfall where `"command": "python3"` resolves to a project virtual environment's Python (which lacks `kimi-swarm`), causing the MCP connection to fail when running `kimi` outside the install folder.

### Fixed

- **MCP server only worked from the repo folder** — The root cause was `DEFAULT_STATE_PATH = Path(".kimi-swarm-state.json")`, a relative path that placed swarm state in whatever directory `kimi` happened to be running in. When users initialized a swarm in one folder and opened Kimi elsewhere, the MCP server couldn't find the state file and appeared broken. Fixed by changing the default state path to a global location (`~/.kimi/kimi-swarm-state.json`). The dashboard meta file also moved to `~/.kimi/kimi-swarm-dashboard.json`. Parent directories are auto-created on first write.
- **`install.sh` now always refreshes MCP registration** — Previously, if `kimi-swarm` was already in `~/.kimi/mcp.json`, the script skipped updating it. This meant broken or stale paths (e.g., `python3` resolving to the wrong interpreter) were never fixed on reinstall. The script now always overwrites the entry with the detected `$PYTHON` full path.
- **Startup hook and skill docs used CWD-relative state path** — Updated `hooks/swarm-startup.sh`, the embedded hook in `install.sh`, and `skills/kimi-swarm/SKILL.md` to check `~/.kimi/kimi-swarm-state.json` instead of `$CWD/.kimi-swarm-state.json`.
- **`--version` flag missing from CLI** — `kimi-swarm --version` now correctly outputs `kimi-swarm 0.1.0`. Previously the flag was unimplemented, causing the install script to display `Version: unknown`.
- **MCP dependency not auto-installed** — `install.sh` now explicitly checks if the `mcp` package is importable and installs it if missing. Previously, installing from git+https with older pip could leave the `mcp` dependency unresolved, causing the MCP server smoke test to fail with "The 'mcp' package may be missing."
- **Missing `mcp` dependency** — Added `mcp>=1.0.0` to `pyproject.toml` so the MCP server imports correctly in fresh environments.
- **`install.sh` now bootstraps full Kimi Code CLI integration** — Previously only installed the Python package and registered the MCP server. Now it also:
  - Installs the `kimi-swarm` skill file to `~/.kimi/skills/kimi-swarm/SKILL.md`
  - Installs the session-startup hook to `~/.kimi/hooks/swarm-startup.sh`
  - Checks `~/.kimi/config.toml` for the `SessionStart` hook entry and warns if missing

### Added

- **Rich agent details in live web dashboard** — Agent cards now display:
  - Prompt / Completion / Total token breakdown
  - Messages count
  - Agent ID (shortened)
  - Uptime (live-computed from spawn time)
  - Spawned timestamp (relative formatting: "2h ago", "just now")
  - Last active timestamp (relative formatting)
  - Task status (`pending` / `in_progress` / `completed` / `failed`)
  - Task description
  - New `.details-grid` CSS section with compact styling
  - `formatDuration()` and `formatTime()` JavaScript helpers for human-readable timestamps

- **Rich agent details in markdown display** — The `KimiDisplay.status_to_markdown()` table now includes:
  - `Prompt / Comp` column showing prompt vs completion token breakdown
  - `Msg` column showing messages count
  - `Uptime` column showing agent lifetime (`Xs`, `Xm Xs`, or `Xh Xm`)
  - `Task` column showing the current task description (truncated to 30 chars)

- **`uptime_seconds` in API serialization** — `AgentStatus.to_dict()` now includes the computed `uptime_seconds` property so API consumers and dashboards receive it directly.

### Fixed

- **`ContextWindow.to_dict()` missing `usage_percent`** — The dashboard JavaScript expected `main_context.usage_percent` and `ctx.usage_percent`, but the model's `to_dict()` only serialized `used_tokens` and `max_tokens`. This caused a JS TypeError that crashed the update loop, preventing agent cards from rendering and leaving the context bar stuck at `0 / 0`. Fixed by adding `usage_percent` to `ContextWindow.to_dict()`.
- **Dashboard server single-threaded blocking** — The dashboard used `HTTPServer`, which processes requests sequentially. An active SSE connection held the handler open in a `while True` loop, blocking all other requests (including `/api/status` and new page loads). Fixed by switching to `ThreadingHTTPServer` so the dashboard can serve multiple concurrent clients.

### Added

- **Dashboard verification script (`scripts/verify_dashboard.py`)** — A Playwright-based end-to-end test that deploys a live swarm, starts the dashboard, and verifies the UI updates in real time. It checks:
  - SSE connection establishment
  - Swarm overview stats (active agents, max capacity, tasks)
  - Agent card rendering with names, phases, progress bars, context usage
  - Live updates to progress and phase while the page is open
  - Token and context stats after task execution
  - Overall progress ring and main context bar
  - Offline overlay behavior
  - Terminated agent reflection
  - API `/api/status` endpoint
  - Captures screenshots at each stage for visual evidence

### Changed

- **Dashboard mini-grid layout** — Expanded from 2-column to 3-column grid to accommodate Prompt, Completion, Total, Ctx Used, Ctx Max, and Messages stats.
- **Dashboard model line** — Simplified to show only the model mapping; messages count moved to its own mini-stat cell.
- **Defensive dashboard JavaScript** — Added fallback calculations for `usage_percent` in the embedded dashboard HTML so the UI gracefully handles state that may lack pre-computed percentages.
