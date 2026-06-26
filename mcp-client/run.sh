#!/usr/bin/env bash
# Launch the Agentregistry Workshop MCP Client (Streamlit) locally.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# (Re)install deps only when requirements.txt changes.
HASH_FILE="$VENV_DIR/.requirements_hash"
CURRENT_HASH=$(md5sum requirements.txt 2>/dev/null || md5 -q requirements.txt 2>/dev/null || echo unknown)
STORED_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo none)
if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
  echo "Installing dependencies..."
  pip install -q -r requirements.txt
  echo "$CURRENT_HASH" > "$HASH_FILE"
fi

PORT="${PORT:-8501}"
echo "Starting Agentregistry Workshop MCP Client..."
echo "Open http://localhost:${PORT} in your browser"
echo
exec streamlit run Homepage.py --server.port "$PORT"
