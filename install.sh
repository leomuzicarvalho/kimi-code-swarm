#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Kimi Swarm CLI — Local Installer
# ------------------------------------------------------------------------------
# Installs the swarm orchestration framework directly into the active Python
# environment (the one Kimi Code is running in) so `kimi-swarm` is available
# immediately in this shell and in Kimi Code terminal sessions.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash
#   # or, for a specific branch:
#   curl -sSL ... | bash -s -- --branch dev
# ------------------------------------------------------------------------------

set -euo pipefail

REPO_URL="https://github.com/leomuzicarvalho/kimi-code-swarm.git"
BRANCH="main"
INSTALL_USER=""
USE_VENV=""
VENV_PATH=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()  { printf "${BLUE}[kimi-swarm]${NC} %s\n" "$1"; }
log_ok()    { printf "${GREEN}[kimi-swarm]${NC} %s\n" "$1"; }
log_warn()  { printf "${YELLOW}[kimi-swarm]${NC} %s\n" "$1"; }
log_err()   { printf "${RED}[kimi-swarm]${NC} %s\n" "$1"; }

usage() {
    cat <<EOF
Usage: install.sh [OPTIONS]

Options:
  --branch <name>     Install from a specific git branch (default: main)
  --user              Install with pip --user (no sudo needed)
  --venv <path>       Install into a new/existing virtualenv at <path>
  --help              Show this message

Examples:
  # Install into current Python environment (Kimi Code's env)
  ./install.sh

  # Install into ~/.local (no root)
  ./install.sh --user

  # Install into a dedicated venv
  ./install.sh --venv ~/.venvs/kimi-swarm
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)
            BRANCH="$2"; shift 2 ;;
        --user)
            INSTALL_USER="--user"; shift ;;
        --venv)
            USE_VENV="1"
            VENV_PATH="$2"; shift 2 ;;
        --help)
            usage; exit 0 ;;
        *)
            log_err "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ------------------------------------------------------------------------------
# Detect Python
# ------------------------------------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [[ -z "$PYTHON" ]]; then
    log_err "Python is not installed or not in PATH."
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
log_info "Detected Python $PY_VERSION at $(command -v "$PYTHON")"

if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    : # ok
else
    log_err "Python 3.10+ is required. Found $PY_VERSION."
    exit 1
fi

# ------------------------------------------------------------------------------
# Virtualenv mode
# ------------------------------------------------------------------------------
if [[ -n "$USE_VENV" ]]; then
    log_info "Virtualenv mode: $VENV_PATH"
    if [[ ! -d "$VENV_PATH" ]]; then
        log_info "Creating virtualenv at $VENV_PATH ..."
        "$PYTHON" -m venv "$VENV_PATH"
    fi
    # shellcheck source=/dev/null
    source "$VENV_PATH/bin/activate"
    PYTHON="$VENV_PATH/bin/python"
    log_ok "Activated venv: $VENV_PATH"
fi

# ------------------------------------------------------------------------------
# Ensure pip is usable
# ------------------------------------------------------------------------------
if ! "$PYTHON" -m pip --version &>/dev/null; then
    log_warn "pip not found. Installing pip ..."
    "$PYTHON" -m ensurepip --upgrade || {
        log_err "Could not install pip. Please install pip manually."
        exit 1
    }
fi

# ------------------------------------------------------------------------------
# Install kimiswarm from GitHub
# ------------------------------------------------------------------------------
log_info "Installing kimi-swarm from ${REPO_URL}@${BRANCH} ..."

# Build the pip install spec
if [[ "$BRANCH" == "main" ]]; then
    PIP_SPEC="git+${REPO_URL}"
else
    PIP_SPEC="git+${REPO_URL}@${BRANCH}"
fi

# Install
if [[ -n "$INSTALL_USER" ]]; then
    "$PYTHON" -m pip install "$PIP_SPEC" $INSTALL_USER --quiet
else
    "$PYTHON" -m pip install "$PIP_SPEC" --quiet
fi

log_ok "Package installed successfully."

# ------------------------------------------------------------------------------
# Verify CLI is available
# ------------------------------------------------------------------------------
if command -v kimi-swarm &>/dev/null; then
    CLI_PATH=$(command -v kimi-swarm)
    CLI_VERSION=$(kimi-swarm --version 2>/dev/null || echo "unknown")
    log_ok "CLI found: $CLI_PATH"
    log_info "Version: $CLI_VERSION"
else
    log_warn "'kimi-swarm' command not found in PATH after installation."
    log_info "Attempting to locate it ..."

    # Try to find it in the Python environment
    SWARM_BIN=$("$PYTHON" -c "import kimi_swarm.cli, os, sys; print(os.path.join(os.path.dirname(sys.executable), 'kimi-swarm'))" 2>/dev/null || true)
    if [[ -x "$SWARM_BIN" ]]; then
        log_info "Found at: $SWARM_BIN"
        log_warn "Add '$(dirname "$SWARM_BIN")' to your PATH, or symlink it:"
        echo "  ln -s $SWARM_BIN /usr/local/bin/kimi-swarm"
    else
        log_warn "You may need to add Python's script directory to PATH:"
        "$PYTHON" -c "import os, sys; print('  export PATH=\"' + os.path.join(os.path.dirname(sys.executable), 'bin') + ':$PATH\"')"
    fi
fi

# ------------------------------------------------------------------------------
# Register MCP server with Kimi Code CLI
# ------------------------------------------------------------------------------
KIMI_MCP_JSON="$HOME/.kimi/mcp.json"
KIMI_DIR="$HOME/.kimi"

if [[ -d "$KIMI_DIR" ]]; then
    log_info "Kimi Code CLI detected. Registering MCP server ..."

    MCP_REGISTERED=false
    if [[ -f "$KIMI_MCP_JSON" ]]; then
        # Backup existing config
        cp "$KIMI_MCP_JSON" "$KIMI_MCP_JSON.backup.$(date +%s)"

        # Check if already registered
        if "$PYTHON" -c "import json,sys; d=json.load(open('$KIMI_MCP_JSON')); sys.exit(0 if 'kimi-swarm' in d.get('mcpServers',{}) else 1)" 2>/dev/null; then
            log_ok "MCP server already registered in $KIMI_MCP_JSON"
            MCP_REGISTERED=true
        else
            # Add kimi-swarm to existing mcpServers
            "$PYTHON" -c "
import json
with open('$KIMI_MCP_JSON') as f:
    config = json.load(f)
if 'mcpServers' not in config:
    config['mcpServers'] = {}
config['mcpServers']['kimi-swarm'] = {
    'command': '$PYTHON',
    'args': ['-m', 'kimi_swarm.mcp_server'],
    'autoStart': True
}
with open('$KIMI_MCP_JSON', 'w') as f:
    json.dump(config, f, indent=2)
print('Added kimi-swarm to mcpServers')
" 2>/dev/null && {
                log_ok "MCP server registered in $KIMI_MCP_JSON"
                MCP_REGISTERED=true
            }
        fi
    else
        # Create new mcp.json
        "$PYTHON" -c "
import json
config = {'mcpServers': {'kimi-swarm': {
    'command': '$PYTHON',
    'args': ['-m', 'kimi_swarm.mcp_server'],
    'autoStart': True
}}}
with open('$KIMI_MCP_JSON', 'w') as f:
    json.dump(config, f, indent=2)
print('Created mcp.json with kimi-swarm server')
" 2>/dev/null && {
            log_ok "Created $KIMI_MCP_JSON with kimi-swarm MCP server"
            MCP_REGISTERED=true
        }
    fi

        if [[ "$MCP_REGISTERED" != "true" ]]; then
        log_warn "Could not automatically register MCP server."
        log_info "Add this manually to $KIMI_MCP_JSON:"
        cat <<EOF
{
  "mcpServers": {
    "kimi-swarm": {
      "command": "$PYTHON",
      "args": ["-m", "kimi_swarm.mcp_server"],
      "autoStart": true
    }
  }
}
EOF
    fi

    # --------------------------------------------------------------------------
    # Install skill file
    # --------------------------------------------------------------------------
    SKILL_DIR="$HOME/.kimi/skills/kimi-swarm"
    mkdir -p "$SKILL_DIR"
    cat > "$SKILL_DIR/SKILL.md" <<'SKILLEOF'
---
name: kimi-swarm
description: Orchestrate multi-agent swarms using the kimi-swarm MCP server. Spawn agents, manage tasks, track progress, and monitor context windows across agents. Use when the user asks about swarms, agents, distributed tasks, parallel coding, or wants to view swarm status.
---

# Kimi Swarm Orchestration

Coordinate intelligent multi-agent swarms via the `kimi-swarm` MCP server.

## Startup Status

To see swarm status automatically when starting a session, add a `SessionStart` hook in `~/.kimi/config.toml`:

```toml
[[hooks]]
event = "SessionStart"
matcher = "startup|resume"
command = """python3 -c "import json,sys,os,subprocess; d=json.load(sys.stdin); c=d.get('cwd',''); p=os.path.join(c,'.kimi-swarm-state.json'); os.path.exists(p) and (print('\n🐝 Active swarm detected in',c), subprocess.run(['kimi-swarm','status','--kimi-display'],cwd=c))" """
```

If you see swarm status at startup, the swarm is already active and ready for commands.

## Sticky Live Status (Todo List Sync)

**Every swarm tool response now includes a `todos` array.** After **every** swarm operation (`swarm_init`, `agent_spawn`, `agent_execute`, `agent_assign`, `agent_progress`, `agent_phase`, `agent_terminate`, `swarm_shutdown`), call `SetTodoList` with the `todos` from the response. This keeps an up-to-date swarm status pinned in Kimi's toolbar (web UI) and as a display block in the conversation (shell UI).

Example workflow:
```
swarm_init(topology="hierarchical", max_agents=5)
→ response contains todos → SetTodoList(todos=response.todos)

agent_spawn(agent_type="coder", name="fe-dev", model="sonnet")
→ response contains todos → SetTodoList(todos=response.todos)
```

The todo list shows:
- Swarm header with agent count and overall progress
- Each agent as a todo item with phase and progress bar
- Auto-updating status as agents move through phases

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `swarm_init` | Create a new swarm (hierarchical/mesh/consensus) |
| `swarm_status` | Get full status with markdown + todo-sync data |
| `swarm_shutdown` | Shutdown swarm, optionally clear state |
| `agent_spawn` | Spawn an agent with type, name, model |
| `agent_execute` | Run a task on an agent |
| `agent_assign` | Assign a task without executing |
| `agent_progress` | Update agent progress 0-100 |
| `agent_phase` | Set agent phase (idle/planning/executing/etc) |
| `agent_terminate` | Terminate an agent |
| `agent_list` | List all agents |
| `swarm_demo` | Run a quick demo swarm |

## Model Mapping

| Alias | Resolved Kimi Model | Context |
|-------|---------------------|---------|
| `haiku` | `moonshot-v1-8k` | 8,192 |
| `sonnet` | `kimi-k2.6` | 256,000 |
| `opus` | `kimi-k2-0712-preview` | 128,000 |
| `inherit` | `kimi-k2.6` | 256,000 |

## Core Workflow

1. **Initialize**: `swarm_init` with topology and max_agents
2. **Sync todos**: `SetTodoList(todos=response.todos)` ← always do this
3. **Spawn agents**: `agent_spawn` for each role
4. **Sync todos**: `SetTodoList(todos=response.todos)` ← always do this
5. **Execute**: `agent_execute` or `agent_assign` + `agent_progress`
6. **Sync todos**: `SetTodoList(todos=response.todos)` ← always do this
7. **Monitor**: `swarm_status` anytime; sync todos to refresh sticky display
8. **Cleanup**: `swarm_shutdown` when done

## Quick Patterns

**Parallel coding swarm:**
```
swarm_init(topology="hierarchical", max_agents=5)
SetTodoList(todos=response.todos)
agent_spawn(agent_type="architect", name="arch-1", model="sonnet")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="coder", name="fe-dev", model="sonnet")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="coder", name="be-dev", model="haiku")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="tester", name="qa-1", model="haiku")
SetTodoList(todos=response.todos)
agent_spawn(agent_type="reviewer", name="sec-1", model="sonnet")
SetTodoList(todos=response.todos)
agent_execute(agent_id="fe-dev-id", prompt="Build login page")
SetTodoList(todos=response.todos)
agent_execute(agent_id="be-dev-id", prompt="Implement auth API")
SetTodoList(todos=response.todos)
```

## Display

Always render the `markdown` field from `swarm_status` or `swarm_init` directly — it contains a formatted table with progress bars, context usage, and phase emojis. Additionally, always sync the `todos` array to `SetTodoList` so the swarm status stays sticky and live-updating in the conversation window.
SKILLEOF
    log_ok "Skill installed to $SKILL_DIR/SKILL.md"

    # --------------------------------------------------------------------------
    # Install startup hook
    # --------------------------------------------------------------------------
    HOOK_DIR="$HOME/.kimi/hooks"
    mkdir -p "$HOOK_DIR"
    cat > "$HOOK_DIR/swarm-startup.sh" <<'HOOKEOF'
#!/bin/bash
# Kimi Swarm Startup Hook — auto-displays swarm status on SessionStart
# Reads hook context from stdin, checks for active swarm, outputs markdown status.

read -r JSON

CWD=$(echo "$JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)
SOURCE=$(echo "$JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('source','startup'))" 2>/dev/null)

if [ -z "$CWD" ]; then
    CWD="$(pwd)"
fi

STATE_FILE="$CWD/.kimi-swarm-state.json"

if [ ! -f "$STATE_FILE" ]; then
    # No active swarm in this directory — silent exit
    exit 0
fi

# Check if swarm is active
IS_ACTIVE=$(python3 -c "
import json, sys
try:
    with open('$STATE_FILE') as f:
        data = json.load(f)
    print('true' if data.get('is_active', False) else 'false')
except:
    print('false')
")

if [ "$IS_ACTIVE" != "true" ]; then
    exit 0
fi

# Output swarm status markdown using the installed CLI
echo ""
echo "🐝 **Active Swarm Detected**"
echo ""

kimi-swarm status --kimi-display 2>/dev/null

exit 0
HOOKEOF
    chmod +x "$HOOK_DIR/swarm-startup.sh"
    log_ok "Startup hook installed to $HOOK_DIR/swarm-startup.sh"

    # --------------------------------------------------------------------------
    # Check config.toml for SessionStart hook
    # --------------------------------------------------------------------------
    KIMI_CONFIG="$HOME/.kimi/config.toml"
    if [[ -f "$KIMI_CONFIG" ]]; then
        if grep -q "swarm-startup.sh" "$KIMI_CONFIG" 2>/dev/null; then
            log_ok "SessionStart hook already configured in config.toml"
        else
            log_warn "SessionStart hook not found in ~/.kimi/config.toml"
            log_info "Add this to get auto-status on session resume:"
            cat <<'EOF'

[[hooks]]
event = "SessionStart"
matcher = "startup|resume"
command = "bash /Users/leonardomuzi/.kimi/hooks/swarm-startup.sh"
timeout = 10

EOF
        fi
    else
        log_warn "~/.kimi/config.toml not found. Cannot verify SessionStart hook."
    fi
else
    log_info "Kimi Code CLI not detected (~/.kimi not found). MCP server not registered."
    log_info "If you use Kimi Code CLI, manually add the server to ~/.kimi/mcp.json"
fi

# ------------------------------------------------------------------------------
# Ensure MCP dependency is available
# ------------------------------------------------------------------------------
log_info "Checking MCP dependency ..."
if ! "$PYTHON" -c "import mcp" 2>/dev/null; then
    log_warn "MCP package not found. Installing explicitly ..."
    "$PYTHON" -m pip install "mcp>=1.0.0" --quiet
fi

# ------------------------------------------------------------------------------
# Quick smoke test
# ------------------------------------------------------------------------------
log_info "Running smoke tests ..."

# CLI smoke test
CLI_DEMO_OUTPUT=$(kimi-swarm demo 2>&1) || true
if echo "$CLI_DEMO_OUTPUT" | grep -q "Demo complete"; then
    log_ok "CLI smoke test passed!"
else
    log_warn "CLI smoke test had issues (expected if no swarm is active)."
fi

# MCP server smoke test
MCP_IMPORT_OUTPUT=$("$PYTHON" -c "from kimi_swarm.mcp_server import main; print('MCP server import OK')" 2>&1) || true
if echo "$MCP_IMPORT_OUTPUT" | grep -q "MCP server import OK"; then
    log_ok "MCP server import test passed!"
else
    log_err "MCP server import failed. The 'mcp' package may be missing."
    log_info "Diagnostics:"
    echo "  $MCP_IMPORT_OUTPUT"
    log_info "Try: $PYTHON -m pip install mcp"
fi

# ------------------------------------------------------------------------------
# Print next steps
# ------------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "${GREEN}✅ kimi-swarm installed successfully!${NC}\n"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_info "Quick start:"
echo ""
echo "  # Initialize a swarm"
echo "  kimi-swarm init --topology hierarchical --max-agents 5"
echo ""
echo "  # Spawn agents"
echo "  kimi-swarm spawn --type coder --name dev-1 --model sonnet"
echo "  kimi-swarm spawn --type tester --name qa-1 --model haiku"
echo ""
echo "  # View status in Kimi's window"
echo "  kimi-swarm status --kimi-display"
echo ""
echo "  # Run a full demo"
echo "  kimi-swarm demo"
echo ""

if [[ -n "$USE_VENV" ]]; then
    echo "💡 You installed into a venv. To use it in Kimi Code sessions:"
    echo "   source $VENV_PATH/bin/activate"
    echo ""
fi
