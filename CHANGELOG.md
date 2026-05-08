# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
