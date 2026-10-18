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

# Resolve ownership before any install, repair or uninstall. Never bootstrap pip
# into a user site, venv or externally managed Python.
UV_AVAILABLE=false
PIPX_AVAILABLE=false
UV_OWNS=false
PIPX_OWNS=false
PIPX=(pipx)
UV_PYTHON_READY=false
if command -v uv >/dev/null 2>&1; then
    UV_AVAILABLE=true
    if ! UV_TOOLS=$(uv tool list 2>/dev/null); then
        echo "Error: uv ownership could not be read. No changes were made." >&2
        exit 1
    fi
    if printf '%s\n' "$UV_TOOLS" | grep -Eq '(^|[[:space:]])deepr-research([[:space:]]|$)'; then UV_OWNS=true; fi
fi
if command -v pipx >/dev/null 2>&1; then
    PIPX_AVAILABLE=true
elif command -v python3 >/dev/null 2>&1 && python3 -m pipx --version >/dev/null 2>&1; then
    PIPX_AVAILABLE=true
    PIPX=(python3 -m pipx)
fi
if [ "$PIPX_AVAILABLE" = true ]; then
    if ! PIPX_TOOLS=$("${PIPX[@]}" list 2>/dev/null); then
        echo "Error: pipx ownership could not be read. No changes were made." >&2
        exit 1
    fi
    if printf '%s\n' "$PIPX_TOOLS" | grep -Eq '(^|[[:space:]])deepr-research([[:space:]]|$)'; then PIPX_OWNS=true; fi
fi
if [ "$UV_OWNS" = true ] && [ "$PIPX_OWNS" = true ]; then
    echo "Error: both uv and pipx own Deepr. Remove the unwanted copy explicitly before retrying." >&2
    exit 1
fi
MANAGER=""
if [ "$UV_OWNS" = true ]; then MANAGER=uv
elif [ "$PIPX_OWNS" = true ]; then MANAGER=pipx
elif command -v "$CLI" >/dev/null 2>&1; then
    echo "Error: Deepr exists outside the detected tool managers. Update or remove that copy explicitly." >&2
    exit 1
fi
# A managed copy must also be the visible command; do not update a shadowed copy.
if [ -n "$MANAGER" ] && command -v "$CLI" >/dev/null 2>&1; then
    if [ "$MANAGER" = uv ]; then MANAGED_BIN=$(uv tool dir --bin)
    else MANAGED_BIN=$("${PIPX[@]}" environment --value PIPX_BIN_DIR); fi
    if [ -z "$MANAGED_BIN" ] || [ "$(command -v "$CLI")" != "$MANAGED_BIN/$CLI" ]; then
        echo "Error: the visible Deepr command shadows the $MANAGER installation. Resolve PATH or remove that copy explicitly." >&2
        exit 1
    fi
fi
if [ "${1:-}" = "--uninstall" ]; then
    if [ "$MANAGER" = uv ]; then uv tool uninstall "$PACKAGE"
    elif [ "$MANAGER" = pipx ]; then "${PIPX[@]}" uninstall "$PACKAGE"
    else echo "No managed Deepr installation found."; exit 0; fi
    echo "Uninstalled. Your reports, experts and configuration are untouched."
    exit 0
fi
if [ -z "$MANAGER" ]; then
    if [ "$UV_AVAILABLE" = true ]; then MANAGER=uv
    elif [ "$PIPX_AVAILABLE" = true ]; then MANAGER=pipx
    else
        echo "Error: install uv (recommended) or pipx through its official instructions, then retry." >&2
        echo "https://docs.astral.sh/uv/getting-started/installation/" >&2
        echo "https://pipx.pypa.io/stable/installation/" >&2
        exit 1
    fi
fi

# Stable CI-supported CPython only; pipx must receive an explicit interpreter.
PYTHON_PROBE='
import sys
ok = sys.implementation.name == "cpython" and sys.version_info[:2] in {(3,11),(3,12),(3,13),(3,14),(3,15)} and sys.version_info.releaselevel == "final"
print(getattr(sys, "_base_executable", sys.executable)) if ok else None
raise SystemExit(not ok)
'
PYTHON=""
for candidate in python3.15 python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "$PYTHON_PROBE" >/dev/null 2>&1; then
        PYTHON=$candidate
        break
    fi
done
# --force does not migrate an existing pipx environment to --python.
PIPX_PYTHON=""
if [ "$MANAGER" = pipx ]; then
    if [ -n "$PYTHON" ]; then
        PIPX_PYTHON=$("$PYTHON" -c "$PYTHON_PROBE" 2>/dev/null) || PIPX_PYTHON=""
    fi
    if [ "$PIPX_OWNS" = true ]; then
        OWNED_BASE=""
        if PIPX_VENVS=$("${PIPX[@]}" environment --value PIPX_LOCAL_VENVS 2>/dev/null) && [[ "$PIPX_VENVS" = /* ]]; then
            OWNED_PYTHON="$PIPX_VENVS/$PACKAGE/bin/python"
            OWNED_BASE=$("$OWNED_PYTHON" -c "$PYTHON_PROBE" 2>/dev/null) || OWNED_BASE=""
        fi
        if [ -z "$OWNED_BASE" ]; then
            echo "Error: the existing pipx environment does not have a verifiable stable CPython 3.11, 3.12, 3.13, 3.14 or 3.15. No changes were made." >&2
            if [ -z "$PIPX_PYTHON" ]; then
                PIPX_PYTHON=/path/to/supported/python3.15
                echo "Install a supported stable interpreter and replace /path/to/supported/python3.15 with its executable." >&2
            fi
            echo "Rebuild it explicitly with a supported interpreter:" >&2
            printf ' ' >&2
            printf ' %q' "${PIPX[@]}" reinstall "$PACKAGE" --python "$PIPX_PYTHON" >&2
            printf '\n' >&2
            echo "Then rerun this installer to update the recorded package source to the latest release." >&2
            exit 1
        fi
        PIPX_PYTHON=$OWNED_BASE
        PYTHON=$OWNED_PYTHON
    elif [ -z "$PIPX_PYTHON" ]; then
        echo "Error: pipx requires stable CPython 3.11, 3.12, 3.13, 3.14 or 3.15. Install a supported interpreter and retry." >&2
        exit 1
    fi
fi

# --- Resolve the latest versioned wheel from GitHub Releases ---------------
if ! RELEASE_JSON=$(curl -fsSL --connect-timeout 10 --max-time 30 \
    -H "Accept: application/vnd.github+json" \
    -H "User-Agent: deepr-installer" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$RELEASE_API"); then
    echo "Error: could not reach GitHub Releases. No Deepr installation changes were made." >&2
    echo "Check your connection or try again after GitHub is reachable." >&2
    exit 1
fi

if [ -z "$PYTHON" ]; then
    uv python install 3.15
    UV_PYTHON_READY=true
    PYTHON=$(uv python find --managed-python 3.15)
fi

if ! RELEASE_INFO=$(printf '%s' "$RELEASE_JSON" | "$PYTHON" -c '
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
    echo "No Deepr installation changes were made. Try a source install from the release tag." >&2
    exit 1
fi

RELEASE_TAG=${RELEASE_INFO%%$'\t'*}
WHEEL_URL=${RELEASE_INFO#*$'\t'}
if [ -z "$RELEASE_TAG" ] || [ -z "$WHEEL_URL" ] || [[ "$WHEEL_URL" != "$RELEASE_ASSET_PREFIX"* ]]; then
    echo "Error: GitHub returned invalid release metadata. No Deepr installation changes were made." >&2
    exit 1
fi
step "Resolved $RELEASE_TAG from GitHub Releases."

# Keep manager and interpreter choice identical through install and repair.
if [ "$MANAGER" = uv ]; then
    if [ "$UV_PYTHON_READY" = false ]; then uv python install 3.15; fi
    INSTALL=(uv tool install --python 3.15 --managed-python)
    REMOVE=(uv tool uninstall)
else
    INSTALL=("${PIPX[@]}" install --python "$PIPX_PYTHON")
    REMOVE=("${PIPX[@]}" uninstall)
fi
step "Installing or updating $PACKAGE via $MANAGER from $RELEASE_TAG ..."
if ! "${INSTALL[@]}" --force "$WHEEL_URL"; then
    step "Install failed; repairing with the same manager and interpreter ..."
    "${REMOVE[@]}" "$PACKAGE" || true
    "${INSTALL[@]}" "$WHEEL_URL"
fi

deepr_works() { command -v "$CLI" >/dev/null 2>&1 && "$CLI" --version >/dev/null 2>&1; }
if ! deepr_works; then
    step "$CLI did not run cleanly; attempting one clean reinstall via $MANAGER ..."
    "${REMOVE[@]}" "$PACKAGE" || true
    "${INSTALL[@]}" "$WHEEL_URL"
fi
if ! deepr_works; then
    echo "Install completed but '$CLI' still does not run. Check PATH or rerun this installer to repair via $MANAGER." >&2
    exit 1
fi
"$CLI" --version
shown_version=true

echo ""
echo "==> Done."
echo ""
echo "Next steps:"
[ "$shown_version" = true ] || echo "  0. Open a new terminal (so PATH picks up $CLI)"
echo "  1. $CLI init"
echo "  2. $CLI doctor"
echo "  3. Configure owned-local Ollama or a safety-eligible plan CLI"
echo "  4. Keep the repository-wide ceiling at or below: $CLI budget set 5"
echo ""
echo "Quick start:"
echo "  $CLI capacity"
echo ""
echo "Update later:  re-run this one-liner, or '$CLI upgrade'"
echo "Uninstall:     re-run this one-liner with -- --uninstall"
echo ""
echo "Dev / editable from source:"
echo "  git clone https://github.com/blisspixel/deepr.git && cd deepr && uv tool install --python 3.15 --managed-python -e ."
echo ""
