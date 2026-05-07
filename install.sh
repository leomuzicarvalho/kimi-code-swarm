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
# Quick smoke test
# ------------------------------------------------------------------------------
log_info "Running smoke test ..."
if kimi-swarm demo >/dev/null 2>&1; then
    log_ok "Smoke test passed!"
else
    log_warn "Smoke test had issues (expected if no swarm is active)."
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
