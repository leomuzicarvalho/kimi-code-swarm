#!/bin/bash
# Kimi Swarm Startup Hook — auto-displays swarm status on SessionStart
# Reads hook context from stdin, checks for active swarm, outputs markdown status.

read -r JSON

CWD=$(echo "$JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)
SOURCE=$(echo "$JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('source','startup'))" 2>/dev/null)

STATE_FILE="$HOME/.kimi/kimi-swarm-state.json"

if [ ! -f "$STATE_FILE" ]; then
    # No active swarm — silent exit
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
