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
$ReleaseApi = "https://api.github.com/repos/blisspixel/deepr/releases/latest"
$ReleaseAssetPrefix = "https://github.com/blisspixel/deepr/releases/download/"

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

# --- Resolve the latest versioned wheel from GitHub Releases ---------------
try {
    $headers = @{
        Accept = "application/vnd.github+json"
        "User-Agent" = "deepr-installer"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    $release = Invoke-RestMethod -Uri $ReleaseApi -Headers $headers -TimeoutSec 30
} catch {
    Write-Err "Error: could not reach GitHub Releases. No installation changes were made."
    Write-Err "Check your connection or try again after GitHub is reachable."
    exit 1
}

if (-not $release.tag_name) {
    Write-Err "Error: GitHub returned release metadata without a version tag."
    Write-Err "No installation changes were made."
    exit 1
}
$releaseTag = [string]$release.tag_name
$releaseVersion = if ($releaseTag.StartsWith("v")) { $releaseTag.Substring(1) } else { $releaseTag }
$expectedAsset = "deepr_research-$releaseVersion-py3-none-any.whl"

$asset = @($release.assets | Where-Object {
    $_.name -eq $expectedAsset -and
    $_.browser_download_url -is [string] -and
    $_.browser_download_url.StartsWith($ReleaseAssetPrefix, [System.StringComparison]::Ordinal)
}) | Select-Object -First 1

if (-not $releaseVersion -or -not $asset) {
    Write-Err "Error: the latest GitHub release has no supported Deepr wheel asset."
    Write-Err "No installation changes were made. Try a source install from the release tag."
    exit 1
}

$wheelUrl = [string]$asset.browser_download_url
Write-Step "Resolved $releaseTag from GitHub Releases."

# --- Ensure pipx ------------------------------------------------------------
& $python -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Step "pipx not found. Installing pipx ..."
    & $python -m pip install --user pipx --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Error: pipx installation failed. No Deepr installation changes were made."
        exit $LASTEXITCODE
    }
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
    $list = & $python -m pipx list 2>$null | Out-String
    if ($list -match [regex]::Escape($Package)) { $installed = $true }
} catch { }

if ($installed) {
    Write-Step "$Package already installed. Updating from $releaseTag ..."
} else {
    Write-Step "Installing $Package from $releaseTag (CLI: $Cli) ..."
}

& $python -m pipx install --force $wheelUrl
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Install failed; repairing the isolated environment ..."
    & $python -m pipx uninstall $Package
    & $python -m pipx install $wheelUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Error: installation from GitHub release $releaseTag failed."
        exit $LASTEXITCODE
    }
}

# --- Verify it runs; one automatic clean reinstall if not -------------------
if (-not (Test-DeeprWorks)) {
    Write-Warn "$Cli did not run cleanly; attempting a clean reinstall ..."
    & $python -m pipx uninstall $Package
    & $python -m pipx install $wheelUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Error: clean installation from GitHub release $releaseTag failed."
        exit $LASTEXITCODE
    }
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
Write-Host "  1. $Cli init"
Write-Host "  2. $Cli doctor"
Write-Host "  3. Configure capacity: local Ollama, a supported plan CLI, or an API provider"
Write-Host "  4. For metered APIs, set a ceiling: $Cli budget set 50"
Write-Host ""
Write-Host "Quick start:"
Write-Host "  $Cli research `"your question`" --auto"
Write-Host ""
Write-Host "Update later:  re-run this one-liner, or '$Cli upgrade'"
Write-Host "Uninstall:     re-run this one-liner with -Uninstall"
Write-Host ""
Write-Host "Dev / editable from source:"
Write-Host "  git clone https://github.com/blisspixel/deepr.git; cd deepr; pipx install -e ."
Write-Host ""
