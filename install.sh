#!/usr/bin/env bash
# One-command installer for the ChimeraX MCP server.
#
# Usage:
#   ./install.sh             # configure Codex (CLI + Desktop app)
#   ./install.sh codex       # same as above, explicit
#   ./install.sh claude-desktop
#   ./install.sh cursor
#
# Run from a clone of the chimeraX-mcp repository. The script:
#   1. Verifies Python 3.11+ is available
#   2. Creates .venv and installs chimerax-mcp into it
#   3. Writes the MCP config for the requested client
#   4. Runs `doctor` to check the environment

set -euo pipefail

CLIENT="${1:-codex}"

info()  { printf '==> %s\n' "$*"; }
warn()  { printf 'WARN: %s\n' "$*" >&2; }
die()   { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# --- sanity checks ----------------------------------------------------------

if [[ ! -f pyproject.toml ]] || ! grep -q '"chimerax-mcp"' pyproject.toml; then
    die "run this from the chimeraX-mcp repository root (pyproject.toml not found)"
fi

if ! command -v python3 >/dev/null 2>&1; then
    cat >&2 <<'EOF'
ERROR: python3 not found on PATH.

Install Python 3.11 or newer:
  macOS:   brew install python@3.12      (or download from https://www.python.org/downloads/)
  Linux:   sudo apt install python3.12   (or your distro's equivalent)
EOF
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    cat >&2 <<EOF
ERROR: Python 3.11 or newer is required, found ${PY_VER}.

Install a newer version:
  macOS:   brew install python@3.12      (or download from https://www.python.org/downloads/)
  Linux:   sudo apt install python3.12   (or your distro's equivalent)

If you already have a newer Python installed under a different name
(e.g. python3.12), create the venv manually:
  python3.12 -m venv .venv && source .venv/bin/activate && pip install .
  chimerax-mcp setup ${CLIENT}
EOF
    exit 1
fi

# --- venv + install ---------------------------------------------------------

if [[ ! -d .venv ]]; then
    info "Creating virtual environment in .venv/"
    python3 -m venv .venv
else
    info "Reusing existing .venv/"
fi

PIP="./.venv/bin/pip"
CHIMERAX_MCP="./.venv/bin/chimerax-mcp"

info "Upgrading pip"
"$PIP" install --quiet --upgrade pip

info "Installing chimerax-mcp"
"$PIP" install --quiet .

if [[ ! -x "$CHIMERAX_MCP" ]]; then
    die "install completed but ${CHIMERAX_MCP} is missing — check pip output above"
fi

# --- client setup -----------------------------------------------------------

info "Writing MCP config for client: ${CLIENT}"
"$CHIMERAX_MCP" setup "$CLIENT"

# --- verification -----------------------------------------------------------

info "Running environment check (doctor)"
# doctor exits non-zero if ChimeraX isn't installed or reachable — informational only,
# not a hard failure, so users can finish setup before launching ChimeraX.
set +e
"$CHIMERAX_MCP" doctor
DOCTOR_STATUS=$?
set -e

echo
info "Install finished"

case "$CLIENT" in
    codex)
        cat <<'EOF'

Next steps for Codex Desktop:
  1. Fully quit Codex.app (Cmd+Q — closing the window is not enough).
  2. Reopen Codex.app.
  3. Ask Codex: "List the ChimeraX tools you have available."

The same ~/.codex/config.toml is used by Codex CLI, so `codex` in a terminal
will see the tools too.
EOF
        ;;
    claude-desktop)
        echo
        echo "Restart Claude Desktop to load the new MCP server."
        ;;
    cursor)
        echo
        echo "Restart Cursor to load the new MCP server."
        ;;
    *)
        echo
        echo "Restart ${CLIENT} to load the new MCP server."
        ;;
esac

if [[ $DOCTOR_STATUS -ne 0 ]]; then
    echo
    warn "doctor reported warnings above (often: ChimeraX not installed or not running)."
    warn "Install UCSF ChimeraX from https://www.cgl.ucsf.edu/chimerax/download.html if needed."
    warn "ChimeraX will auto-launch when the first tool is called, as long as it is installed."
fi
