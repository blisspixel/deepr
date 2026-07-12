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
RELEASE_API="https://api.github.com/repos/blisspixel/deepr/releases/latest"
RELEASE_ASSET_PREFIX="https://github.com/blisspixel/deepr/releases/download/"

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
if ! $PYTHON -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
    echo "Error: Python 3.12+ is required (found $PYVER)." >&2
    exit 1
fi

# --- Resolve the latest versioned wheel from GitHub Releases ---------------
if ! RELEASE_JSON=$(curl -fsSL --connect-timeout 10 --max-time 30 \
    -H "Accept: application/vnd.github+json" \
    -H "User-Agent: deepr-installer" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$RELEASE_API"); then
    echo "Error: could not reach GitHub Releases. No installation changes were made." >&2
    echo "Check your connection or try again after GitHub is reachable." >&2
    exit 1
fi

if ! RELEASE_INFO=$(printf '%s' "$RELEASE_JSON" | $PYTHON -c '
import json
import sys

payload = json.load(sys.stdin)
tag = payload.get("tag_name")
assets = payload.get("assets", [])
url_prefix = "https://github.com/blisspixel/deepr/releases/download/"
if not isinstance(tag, str) or not tag:
    raise SystemExit(1)
version = tag.removeprefix("v")
expected_name = f"deepr_research-{version}-py3-none-any.whl"
wheel = next(
    (
        asset
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("name"), str)
        and asset["name"] == expected_name
        and isinstance(asset.get("browser_download_url"), str)
        and asset["browser_download_url"].startswith(url_prefix)
    ),
    None,
)
if not version or wheel is None:
    raise SystemExit(1)
print(tag, wheel.get("browser_download_url", ""), sep="\t")
'); then
    echo "Error: the latest GitHub release has no supported Deepr wheel asset." >&2
    echo "No installation changes were made. Try a source install from the release tag." >&2
    exit 1
fi

RELEASE_TAG=${RELEASE_INFO%%$'\t'*}
WHEEL_URL=${RELEASE_INFO#*$'\t'}
if [ -z "$RELEASE_TAG" ] || [ -z "$WHEEL_URL" ] || [[ "$WHEEL_URL" != "$RELEASE_ASSET_PREFIX"* ]]; then
    echo "Error: GitHub returned invalid release metadata. No installation changes were made." >&2
    exit 1
fi
step "Resolved $RELEASE_TAG from GitHub Releases."

# --- Ensure pipx ------------------------------------------------------------
if ! $PYTHON -m pipx --version >/dev/null 2>&1; then
    step "pipx not found. Installing pipx ..."
    $PYTHON -m pip install --user pipx
    $PYTHON -m pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- Does the CLI actually run? (used to verify + self-heal) ----------------
deepr_works() { command -v "$CLI" >/dev/null 2>&1 && "$CLI" --version >/dev/null 2>&1; }

# --- Install, update, or repair (idempotent + self-healing) -----------------
if $PYTHON -m pipx list 2>/dev/null | grep -q "$PACKAGE"; then
    step "$PACKAGE already installed. Updating from $RELEASE_TAG ..."
else
    step "Installing $PACKAGE from $RELEASE_TAG (CLI: $CLI) ..."
fi

if ! $PYTHON -m pipx install --force "$WHEEL_URL"; then
    step "Install failed; repairing the isolated environment ..."
    $PYTHON -m pipx uninstall "$PACKAGE" || true
    $PYTHON -m pipx install "$WHEEL_URL"
fi

# --- Verify it runs; one automatic clean reinstall if not -------------------
if ! deepr_works; then
    step "$CLI did not run cleanly; attempting a clean reinstall ..."
    $PYTHON -m pipx uninstall "$PACKAGE" || true
    $PYTHON -m pipx install "$WHEEL_URL"
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
echo "  1. $CLI init"
echo "  2. $CLI doctor"
echo "  3. Configure capacity: local Ollama, a supported plan CLI, or an API provider"
echo "  4. For metered APIs, set a ceiling: $CLI budget set 50"
echo ""
echo "Quick start:"
echo "  $CLI research \"your question\" --auto"
echo ""
echo "Update later:  re-run this one-liner, or '$CLI upgrade'"
echo "Uninstall:     re-run this one-liner with -- --uninstall"
echo ""
echo "Dev / editable from source:"
echo "  git clone https://github.com/blisspixel/deepr.git && cd deepr && pipx install -e ."
echo ""
