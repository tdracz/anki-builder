#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Vocab Builder — one-command launcher (macOS / Linux)
#
# First run:  creates .venv, installs Python + Node deps, builds frontend
# Subsequent: skips steps that are already done, starts the server
#
# Usage:
#   ./run.sh              — start on default port 8000
#   ./run.sh --rebuild    — force frontend rebuild before starting
#   ./run.sh --port 8080  — use a different port
#   ./run.sh --no-browser — don't open the browser automatically
# ---------------------------------------------------------------------------

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# ---- colours ---------------------------------------------------------------
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RESET='\033[0m'

step() { echo -e "${CYAN}▶ $1${RESET}"; }
ok()   { echo -e "${GREEN}✓ $1${RESET}"; }
warn() { echo -e "${YELLOW}⚠ $1${RESET}"; }

# ---- 1. Python virtualenv --------------------------------------------------
if [ ! -f "$PYTHON" ]; then
    step "Creating Python virtual environment…"
    python3 -m venv "$VENV"
    ok "Virtual environment created at .venv/"
else
    ok "Virtual environment already exists"
fi

# ---- 2. Python dependencies ------------------------------------------------
# Use a stamp file so we only reinstall when requirements.txt changes
STAMP="$VENV/.deps_installed"
if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    step "Installing Python dependencies…"
    "$PIP" install -q -r requirements.txt
    touch "$STAMP"
    ok "Python dependencies installed"
else
    ok "Python dependencies up to date"
fi

# ---- 3. Node dependencies --------------------------------------------------
if [ ! -d "frontend/node_modules" ]; then
    step "Installing Node dependencies…"
    npm install --prefix frontend --silent
    ok "Node dependencies installed"
else
    ok "Node dependencies already installed"
fi

# ---- 4. Frontend build (pass --rebuild to force) ---------------------------
# start.py handles the actual build logic; we just forward the flag
EXTRA_ARGS=()
for arg in "$@"; do
    EXTRA_ARGS+=("$arg")
done

# ---- 5. Start ---------------------------------------------------------------
echo ""
echo -e "${GREEN}Starting Vocab Builder…${RESET}"
echo ""

exec "$PYTHON" start.py "${EXTRA_ARGS[@]}"
