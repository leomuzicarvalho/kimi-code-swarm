# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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

### Changed

- **Dashboard mini-grid layout** — Expanded from 2-column to 3-column grid to accommodate Prompt, Completion, Total, Ctx Used, Ctx Max, and Messages stats.
- **Dashboard model line** — Simplified to show only the model mapping; messages count moved to its own mini-stat cell.
