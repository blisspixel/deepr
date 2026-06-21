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

# --- Does the CLI actually run? (used to verify + self-heal) ----------------
deepr_works() { command -v "$CLI" >/dev/null 2>&1 && "$CLI" --version >/dev/null 2>&1; }

# --- Install, update, or repair (idempotent + self-healing) -----------------
if pipx list 2>/dev/null | grep -q "$PACKAGE"; then
    step "$PACKAGE already installed. Updating to the latest version ..."
    # A stale venv (common after a system Python upgrade) makes upgrade fail;
    # fall back to reinstall, then a clean uninstall+install.
    pipx upgrade "$PACKAGE" \
        || { step "Update failed; repairing ..."; pipx reinstall "$PACKAGE"; } \
        || { pipx uninstall "$PACKAGE" || true; pipx install "$PACKAGE"; }
else
    step "Installing $PACKAGE (CLI: $CLI) ..."
    pipx install "$PACKAGE"
fi

# --- Verify it runs; one automatic clean reinstall if not -------------------
if ! deepr_works; then
    step "$CLI did not run cleanly; attempting a clean reinstall ..."
    pipx uninstall "$PACKAGE" || true
    pipx install "$PACKAGE"
fi

# --- Report version + warn about a shadowing (non-pipx) install -------------
shown_version=false
if deepr_works; then
    "$CLI" --version && shown_version=true || true
    src=$(command -v "$CLI" 2>/dev/null || true)
    case "$src" in
        *.local/*|*pipx*) : ;;
        "") : ;;
        *) echo "Note: '$CLI' on PATH resolves to $src, not the pipx-managed copy."
           echo "      If the version above looks wrong, remove it: pip uninstall $PACKAGE (in that Python)." ;;
    esac
else
    echo "Install completed but '$CLI' still does not run. Open a new terminal, or: pipx reinstall $PACKAGE" >&2
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
