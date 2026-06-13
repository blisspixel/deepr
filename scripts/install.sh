#!/usr/bin/env bash
# Deepr installer / updater for macOS / Linux
#
# Install or update (recommended one-liner):
#   curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash
#
# Re-running this script updates an existing install to the latest version.
# Uninstall:
#   curl -fsSL https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.sh | bash -s -- --uninstall

set -euo pipefail

PACKAGE="deepr-research"
CLI="deepr"

step() { printf '==> %s\n' "$1"; }

# --- Uninstall path ---------------------------------------------------------
if [ "${1:-}" = "--uninstall" ]; then
    step "Uninstalling $PACKAGE ..."
    if command -v pipx >/dev/null 2>&1; then
        pipx uninstall "$PACKAGE"
        echo "Uninstalled. (Your reports, experts, and .env are untouched.)"
    else
        echo "pipx not found; nothing to uninstall via pipx."
    fi
    exit 0
fi

# --- Locate a suitable Python ----------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 (3.12+) is required." >&2
    exit 1
fi
PYTHON=python3
PYVER=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
if [ "$(printf '%s\n' "3.12" "$PYVER" | sort -V | head -1)" != "3.12" ]; then
    echo "Error: Python 3.12+ is required (found $PYVER)." >&2
    exit 1
fi

# --- Ensure pipx ------------------------------------------------------------
if ! command -v pipx >/dev/null 2>&1; then
    step "pipx not found. Installing pipx ..."
    $PYTHON -m pip install --user pipx
    $PYTHON -m pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- Install or update (idempotent) ----------------------------------------
if pipx list 2>/dev/null | grep -q "$PACKAGE"; then
    step "$PACKAGE already installed. Updating to the latest version ..."
    pipx upgrade "$PACKAGE"
else
    step "Installing $PACKAGE (CLI: $CLI) ..."
    pipx install "$PACKAGE"
fi

# --- Report installed version (best effort) ---------------------------------
shown_version=false
if command -v "$CLI" >/dev/null 2>&1; then
    "$CLI" --version && shown_version=true || true
fi

echo ""
echo "==> Done."
echo ""
echo "Next steps:"
[ "$shown_version" = true ] || echo "  0. Open a new terminal (so PATH picks up $CLI)"
echo "  1. $CLI doctor"
echo "  2. Add at least one API key (XAI / Gemini / OpenAI / Anthropic) to your .env"
echo "  3. $CLI budget set 50"
echo ""
echo "Quick start:"
echo "  $CLI research \"your question\" --auto"
echo ""
echo "Update later:  re-run this one-liner, or '$CLI upgrade'"
echo "Uninstall:     re-run this one-liner with -- --uninstall"
echo ""
echo "Dev / editable from source:"
echo "  git clone https://github.com/blisspixel/deepr.git && cd deepr/deepr && pipx install -e ."
echo ""
