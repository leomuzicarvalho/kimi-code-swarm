#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Kimi Swarm CLI — Uninstaller
# ------------------------------------------------------------------------------
# Removes the swarm orchestration framework from the active Python environment
# and cleans up Kimi Code CLI integrations (MCP server, skill, hook).
#
# Usage:
#   ./uninstall.sh              # Interactive uninstall with confirmation
#   ./uninstall.sh --yes        # Skip confirmation prompts
#   ./uninstall.sh --purge      # Also remove state file and mcp.json backups
# ------------------------------------------------------------------------------

set -euo pipefail

YES=""
PURGE=""

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
Usage: uninstall.sh [OPTIONS]

Options:
  --yes       Skip confirmation prompts and uninstall immediately
  --purge     Also remove swarm state file and mcp.json backups
  --help      Show this message

Examples:
  # Interactive uninstall (asks for confirmation)
  ./uninstall.sh

  # Uninstall without prompts
  ./uninstall.sh --yes

  # Full cleanup including state and backups
  ./uninstall.sh --yes --purge
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes)
            YES="1"; shift ;;
        --purge)
            PURGE="1"; shift ;;
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

PYTHON_ABS=$(command -v "$PYTHON")
log_info "Detected Python at $PYTHON_ABS"

# ------------------------------------------------------------------------------
# Detect pip
# ------------------------------------------------------------------------------
if ! "$PYTHON" -m pip --version &>/dev/null; then
    log_err "pip is not available for $PYTHON. Cannot uninstall package."
    exit 1
fi

# ------------------------------------------------------------------------------
# Check if package is installed
# ------------------------------------------------------------------------------
PKG_INSTALLED=false
if "$PYTHON" -m pip show "kimi-swarm" &>/dev/null; then
    PKG_INSTALLED=true
    PKG_LOCATION=$("$PYTHON" -m pip show "kimi-swarm" | grep "^Location:" | awk '{print $2}')
fi

# ------------------------------------------------------------------------------
# Summary of what will be removed
# ------------------------------------------------------------------------------
KIMI_DIR="$HOME/.kimi"
MCP_JSON="$KIMI_DIR/mcp.json"
SKILL_DIR="$KIMI_DIR/skills/kimi-swarm"
HOOK_FILE="$KIMI_DIR/hooks/swarm-startup.sh"
STATE_FILE="$KIMI_DIR/kimi-swarm-state.json"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_warn "Uninstall Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [[ "$PKG_INSTALLED" == "true" ]]; then
    echo "  ❌ Python package: kimi-swarm ($PKG_LOCATION)"
else
    echo "  ⚠️  Python package: kimi-swarm (not found)"
fi

if [[ -f "$MCP_JSON" ]]; then
    if grep -q '"kimi-swarm"' "$MCP_JSON" 2>/dev/null; then
        echo "  ❌ MCP server entry: kimi-swarm in $MCP_JSON"
    else
        echo "  ✅ MCP server entry: not present in $MCP_JSON"
    fi
else
    echo "  ⚠️  MCP config: $MCP_JSON not found"
fi

if [[ -d "$SKILL_DIR" ]]; then
    echo "  ❌ Skill directory: $SKILL_DIR"
else
    echo "  ✅ Skill directory: already removed"
fi

if [[ -f "$HOOK_FILE" ]]; then
    echo "  ❌ Startup hook: $HOOK_FILE"
else
    echo "  ✅ Startup hook: already removed"
fi

if [[ -n "$PURGE" ]]; then
    if [[ -f "$STATE_FILE" ]]; then
        echo "  ❌ State file: $STATE_FILE"
    else
        echo "  ✅ State file: not present"
    fi
    BACKUP_COUNT=$(find "$KIMI_DIR" -maxdepth 1 -name 'mcp.json.backup.*' 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$BACKUP_COUNT" -gt 0 ]]; then
        echo "  ❌ mcp.json backups: $BACKUP_COUNT file(s) in $KIMI_DIR"
    else
        echo "  ✅ mcp.json backups: none found"
    fi
fi

echo ""

# ------------------------------------------------------------------------------
# Confirmation
# ------------------------------------------------------------------------------
if [[ -z "$YES" ]]; then
    read -r -p "Proceed with uninstall? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY])
            : # proceed
            ;;
        *)
            log_info "Uninstall cancelled."
            exit 0
            ;;
    esac
fi

# ------------------------------------------------------------------------------
# Uninstall Python package
# ------------------------------------------------------------------------------
if [[ "$PKG_INSTALLED" == "true" ]]; then
    log_info "Uninstalling kimi-swarm package ..."
    "$PYTHON" -m pip uninstall -y "kimi-swarm" 2>/dev/null || {
        log_warn "pip uninstall returned non-zero. Package may already be removed."
    }
    log_ok "Package uninstalled."
else
    log_warn "Package 'kimi-swarm' not found in this Python environment."
fi

# ------------------------------------------------------------------------------
# Remove MCP server entry from mcp.json
# ------------------------------------------------------------------------------
if [[ -f "$MCP_JSON" ]]; then
    if grep -q '"kimi-swarm"' "$MCP_JSON" 2>/dev/null; then
        log_info "Removing kimi-swarm from $MCP_JSON ..."
        "$PYTHON" -c "
import json
import sys

try:
    with open('$MCP_JSON') as f:
        config = json.load(f)
    
    if 'mcpServers' in config and 'kimi-swarm' in config['mcpServers']:
        del config['mcpServers']['kimi-swarm']
        # Remove empty mcpServers dict to keep config tidy
        if not config['mcpServers']:
            del config['mcpServers']
        with open('$MCP_JSON', 'w') as f:
            json.dump(config, f, indent=2)
        print('Removed kimi-swarm from mcpServers')
    else:
        print('kimi-swarm not found in mcpServers')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
" && log_ok "MCP server entry removed."
    else
        log_info "MCP server entry not present — nothing to remove."
    fi
else
    log_warn "$MCP_JSON not found — skipping MCP cleanup."
fi

# ------------------------------------------------------------------------------
# Remove skill directory
# ------------------------------------------------------------------------------
if [[ -d "$SKILL_DIR" ]]; then
    log_info "Removing skill directory $SKILL_DIR ..."
    rm -rf "$SKILL_DIR"
    log_ok "Skill directory removed."
else
    log_info "Skill directory already removed."
fi

# ------------------------------------------------------------------------------
# Remove startup hook
# ------------------------------------------------------------------------------
if [[ -f "$HOOK_FILE" ]]; then
    log_info "Removing startup hook $HOOK_FILE ..."
    rm -f "$HOOK_FILE"
    log_ok "Startup hook removed."
else
    log_info "Startup hook already removed."
fi

# ------------------------------------------------------------------------------
# Purge mode: remove state file and backups
# ------------------------------------------------------------------------------
if [[ -n "$PURGE" ]]; then
    if [[ -f "$STATE_FILE" ]]; then
        log_info "Removing swarm state file $STATE_FILE ..."
        rm -f "$STATE_FILE"
        log_ok "State file removed."
    fi

    BACKUPS=$(find "$KIMI_DIR" -maxdepth 1 -name 'mcp.json.backup.*' 2>/dev/null)
    if [[ -n "$BACKUPS" ]]; then
        log_info "Removing mcp.json backups ..."
        echo "$BACKUPS" | while read -r f; do
            rm -f "$f"
        done
        log_ok "Backup files removed."
    fi
fi

# ------------------------------------------------------------------------------
# Check for leftover CLI command
# ------------------------------------------------------------------------------
if command -v kimi-swarm &>/dev/null; then
    log_warn "'kimi-swarm' is still in PATH at: $(command -v kimi-swarm)"
    log_info "You may need to open a new terminal session for PATH changes to take effect."
fi

# ------------------------------------------------------------------------------
# Done
# ------------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "${GREEN}✅ kimi-swarm uninstalled successfully!${NC}\n"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [[ -n "$PURGE" ]]; then
    log_info "Purge mode was active — all state and backups removed."
fi

log_info "To reinstall, run:"
echo ""
echo "  curl -sSL https://raw.githubusercontent.com/leomuzicarvalho/kimi-code-swarm/main/install.sh | bash"
echo ""
