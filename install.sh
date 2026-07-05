#!/usr/bin/env bash
# install.sh — Install hermes-memory-gbrain into Hermes Agent
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/gbrain"

echo "=== hermes-memory-gbrain installer ==="
echo ""

# Check Hermes is installed
if ! command -v hermes &>/dev/null; then
    echo "⚠️  Hermes CLI not found in PATH. Is Hermes Agent installed?"
    echo "   Install: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
    exit 1
fi

# Check gbrain is installed
if ! command -v gbrain &>/dev/null; then
    echo "⚠️  gbrain CLI not found in PATH."
    echo "   Install: npm install -g gbrain   (or pip install gbrain)"
    exit 1
fi

# Create plugins directory
mkdir -p "$PLUGIN_DIR"

# Copy files
echo "📦 Installing to $PLUGIN_DIR ..."
rsync -a --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache' \
    --exclude 'tests' \
    "$SCRIPT_DIR/" "$PLUGIN_DIR/"

# Activate
echo "⚙️  Activating gbrain memory provider..."
hermes config set memory.provider gbrain

# Verify
echo ""
echo "✅ Installation complete!"
echo ""
echo "   Check status:  hermes memory status"
echo "   Run tests:     cd $SCRIPT_DIR && python -m pytest tests/ -v"
echo ""
echo "   To deactivate: hermes config set memory.provider ''"
