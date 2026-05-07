# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

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
