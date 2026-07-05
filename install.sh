#!/usr/bin/env bash
# install.sh — Install hermes-memory-gbrain into Hermes Agent
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/gbrain"

echo "=== hermes-memory-gbrain installer ==="

# Check Hermes
if ! command -v hermes &>/dev/null; then
    echo "⚠️  Hermes CLI not found."
    exit 1
fi

# Install plugin files
mkdir -p "$PLUGIN_DIR"
echo "📦 Installing to $PLUGIN_DIR ..."
rsync -a --delete \
    --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude '.pytest_cache' --exclude '.venv' --exclude 'tests' \
    "$SCRIPT_DIR/" "$PLUGIN_DIR/"

# Check for brain config
CONFIG="$HERMES_HOME/gbrain.json"
if [ ! -f "$CONFIG" ]; then
    echo ""
    echo "⚙️  No gbrain.json found. Creating template..."
    cat > "$CONFIG" << 'EOF'
{
  "brain_dir": "~/ppy-brain",
  "command": "gbrain",
  "timeout": 30
}
EOF
    echo "   → Edit $CONFIG to set your brain_dir path"
fi

# Activate
hermes config set memory.provider gbrain

echo ""
echo "✅ Done. Check: hermes memory status"
