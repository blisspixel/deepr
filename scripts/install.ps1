# Deepr installer / updater for Windows (PowerShell)
#
# Install or update (recommended one-liner):
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"
#
# Re-running this script updates an existing install to the latest version.
# Uninstall:
#   powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1))) -Uninstall"

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$Package = "deepr-research"
$Cli = "deepr"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host $msg -ForegroundColor Red }

# --- Uninstall path ---------------------------------------------------------
if ($Uninstall) {
    Write-Step "Uninstalling $Package ..."
    if (Get-Command pipx -ErrorAction SilentlyContinue) {
        pipx uninstall $Package
        Write-Ok "Uninstalled. (Your reports, experts, and .env are untouched.)"
    } else {
        Write-Warn "pipx not found; nothing to uninstall via pipx."
    }
    exit 0
}

# --- Locate a suitable Python ----------------------------------------------
$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) { $python = "py" }
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Write-Err "Error: Python 3.12+ is required. Install it from https://www.python.org/downloads/"
    exit 1
}

$ver = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
if (-not $ver -or ([version]$ver -lt [version]"3.12")) {
    Write-Err "Error: Python 3.12+ is required (found $ver)."
    exit 1
}

# --- Ensure pipx ------------------------------------------------------------
if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Step "pipx not found. Installing pipx ..."
    & $python -m pip install --user pipx --quiet
    & $python -m pipx ensurepath
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
}

# --- Does the CLI actually run? (used to verify + self-heal) ----------------
function Test-DeeprWorks {
    if (-not (Get-Command $Cli -ErrorAction SilentlyContinue)) { return $false }
    try {
        & $Cli --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

# --- Install, update, or repair (idempotent + self-healing) -----------------
$installed = $false
try {
    $list = pipx list 2>$null | Out-String
    if ($list -match [regex]::Escape($Package)) { $installed = $true }
} catch { }

if ($installed) {
    Write-Step "$Package already installed. Updating to the latest version ..."
    try {
        pipx upgrade $Package
    } catch {
        # A stale venv (common after a system Python upgrade) makes upgrade fail.
        Write-Warn "Update failed; repairing the install ..."
        try { pipx reinstall $Package } catch { pipx uninstall $Package; pipx install $Package }
    }
} else {
    Write-Step "Installing $Package (CLI: $Cli) ..."
    pipx install $Package
}

# --- Verify it runs; one automatic clean reinstall if not -------------------
if (-not (Test-DeeprWorks)) {
    Write-Warn "$Cli did not run cleanly; attempting a clean reinstall ..."
    try { pipx uninstall $Package } catch { }
    pipx install $Package
}

# --- Report version + warn about a shadowing (non-pipx) install -------------
$shownVersion = $false
if (Test-DeeprWorks) {
    try { & $Cli --version; $shownVersion = $true } catch { }
    $src = (Get-Command $Cli -ErrorAction SilentlyContinue).Source
    if ($src -and $src -notlike "*\.local\*" -and $src -notlike "*pipx*") {
        Write-Warn "Note: '$Cli' on PATH resolves to $src, which is not the pipx-managed copy."
        Write-Warn "If the version above looks wrong, remove that copy: pip uninstall $Package (in that Python)."
    }
} else {
    Write-Err "Install completed but '$Cli' still does not run. Try a new terminal, or: pipx reinstall $Package"
}

Write-Host ""
Write-Ok "==> Done."
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
if (-not $shownVersion) { Write-Host "  0. Open a NEW terminal (so PATH picks up $Cli)" }
Write-Host "  1. $Cli doctor"
Write-Host "  2. Add at least one API key (XAI / Gemini / OpenAI / Anthropic) to your .env"
Write-Host "  3. $Cli budget set 50"
Write-Host ""
Write-Host "Quick start:"
Write-Host "  $Cli research `"your question`" --auto"
Write-Host ""
Write-Host "Update later:  re-run this one-liner, or '$Cli upgrade'"
Write-Host "Uninstall:     re-run this one-liner with -Uninstall"
Write-Host ""
Write-Host "Dev / editable from source:"
Write-Host "  git clone https://github.com/blisspixel/deepr.git; cd deepr/deepr; pipx install -e ."
Write-Host ""
