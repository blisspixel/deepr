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

function Invoke-Pipx {
    if ($script:PipxModule) { & $script:PipxHost -m pipx @args }
    else { & pipx @args }
}
function Test-PipxAvailable($PythonCommand) {
    try {
        & $PythonCommand -m pipx --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

$uvAvailable = [bool](Get-Command uv -ErrorAction SilentlyContinue)
$pipxAvailable = [bool](Get-Command pipx -ErrorAction SilentlyContinue)
$script:PipxModule = $false
$script:PipxHost = "python"
if (-not $pipxAvailable -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $pipxAvailable = Test-PipxAvailable "python"
    $script:PipxModule = $pipxAvailable
}
$uvOwns = $false
$pipxOwns = $false
if ($uvAvailable) {
    $tools = & uv tool list 2>$null | Out-String
    if ($LASTEXITCODE -ne 0) { Write-Err "Error: uv ownership could not be read. No changes were made."; exit 1 }
    $uvOwns = $tools -match '(?m)(^|\s)deepr-research(\s|$)'
}
if ($pipxAvailable) {
    $tools = Invoke-Pipx list 2>$null | Out-String
    if ($LASTEXITCODE -ne 0) { Write-Err "Error: pipx ownership could not be read. No changes were made."; exit 1 }
    $pipxOwns = $tools -match '(?m)(^|\s)deepr-research(\s|$)'
}
if ($uvOwns -and $pipxOwns) {
    Write-Err "Error: both uv and pipx own Deepr. Remove the unwanted copy explicitly before retrying."
    exit 1
}
$manager = if ($uvOwns) { "uv" } elseif ($pipxOwns) { "pipx" } else { "" }
if (-not $manager -and (Get-Command $Cli -ErrorAction SilentlyContinue)) {
    Write-Err "Error: Deepr exists outside the detected tool managers. Update or remove that copy explicitly."
    exit 1
}
$visibleCli = Get-Command $Cli -ErrorAction SilentlyContinue
if ($manager -and $visibleCli) {
    $managedBin = if ($manager -eq "uv") { & uv tool dir --bin } else { Invoke-Pipx environment --value PIPX_BIN_DIR }
    if ($LASTEXITCODE -ne 0 -or -not $managedBin -or -not $visibleCli.Source -or
        -not [string]::Equals([System.IO.Path]::GetFullPath($visibleCli.Source), [System.IO.Path]::GetFullPath((Join-Path $managedBin "$Cli.exe")), [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Err "Error: the visible Deepr command shadows the $manager installation. Resolve PATH or remove that copy explicitly."
        exit 1
    }
}
if ($Uninstall) {
    if ($manager -eq "uv") { & uv tool uninstall $Package }
    elseif ($manager -eq "pipx") { Invoke-Pipx uninstall $Package }
    else { Write-Host "No managed Deepr installation found."; exit 0 }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Ok "Uninstalled. Your reports, experts and configuration are untouched."
    exit 0
}
if (-not $manager) {
    if ($uvAvailable) { $manager = "uv" }
    elseif ($pipxAvailable) { $manager = "pipx" }
    else {
        Write-Err "Error: install uv (recommended) or pipx through its official instructions, then retry."
        Write-Host "https://docs.astral.sh/uv/getting-started/installation/"
        Write-Host "https://pipx.pypa.io/stable/installation/"
        exit 1
    }
}

# Explicitly select stable CI-supported CPython, never arbitrary prerelease PATH Python.
$pythonProbe = "import sys; ok = sys.implementation.name == 'cpython' and sys.version_info[:2] in {(3,11),(3,12),(3,13),(3,14),(3,15)} and sys.version_info.releaselevel == 'final'; print(getattr(sys, '_base_executable', sys.executable)) if ok else None; raise SystemExit(not ok)"
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($version in @("-3.15", "-3.14", "-3.13", "-3.12", "-3.11")) {
        try {
            $candidatePath = & py $version -c $pythonProbe 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidatePath) { $python = $candidatePath; break }
        } catch { }
    }
}
foreach ($candidate in @("python3.15", "python3.14", "python3.13", "python3.12", "python3.11", "python", "py")) {
    if ($python) { break }
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        try {
            & $candidate -c $pythonProbe *> $null
            if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
        } catch { }
    }
}
# --force does not migrate an existing pipx environment to --python.
$pipxPython = $null
if ($manager -eq "pipx") {
    if ($python) {
        try {
            $pipxPython = & $python -c $pythonProbe 2>$null
            if ($LASTEXITCODE -ne 0) { $pipxPython = $null }
        } catch { $pipxPython = $null }
    }
    if ($pipxOwns) {
        $ownedBase = $null
        try {
            $pipxVenvs = Invoke-Pipx environment --value PIPX_LOCAL_VENVS 2>$null
            if ($LASTEXITCODE -eq 0 -and $pipxVenvs -is [string] -and [System.IO.Path]::IsPathRooted($pipxVenvs)) {
                $ownedPython = Join-Path $pipxVenvs "$Package/Scripts/python.exe"
                $ownedBase = & $ownedPython -c $pythonProbe 2>$null
                if ($LASTEXITCODE -ne 0) { $ownedBase = $null }
            }
        } catch { $ownedBase = $null }
        if (-not $ownedBase) {
            Write-Err "Error: the existing pipx environment does not have a verifiable stable CPython 3.11, 3.12, 3.13, 3.14 or 3.15. No changes were made."
            if (-not $pipxPython) {
                $pipxPython = "C:\path\to\supported\python.exe"
                Write-Host "Install a supported stable interpreter and replace C:\path\to\supported\python.exe with its executable."
            }
            $pipxCommand = if ($script:PipxModule) { "& '" + $PipxHost.Replace("'", "''") + "' -m pipx" } else { "pipx" }
            $quotedPython = "'" + $pipxPython.Replace("'", "''") + "'"
            Write-Host "Rebuild it explicitly with a supported interpreter:"
            Write-Host "  $pipxCommand reinstall $Package --python $quotedPython"
            Write-Host "Then rerun this installer to update the recorded package source to the latest release."
            exit 1
        }
        $pipxPython = $ownedBase
    } elseif (-not $pipxPython) {
        Write-Err "Error: pipx requires stable CPython 3.11, 3.12, 3.13, 3.14 or 3.15. Install a supported interpreter and retry."
        exit 1
    }
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

function Invoke-ManagedInstall([switch]$Force) {
    $forceArgs = @()
    if ($Force) { $forceArgs = @("--force") }
    if ($manager -eq "uv") { & uv tool install --python 3.15 --managed-python @forceArgs $wheelUrl }
    else { Invoke-Pipx install --python $pipxPython @forceArgs $wheelUrl }
}
function Remove-ManagedInstall {
    if ($manager -eq "uv") { & uv tool uninstall $Package }
    else { Invoke-Pipx uninstall $Package }
}
if ($manager -eq "uv") {
    & uv python install 3.15
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
function Test-DeeprWorks {
    if (-not (Get-Command $Cli -ErrorAction SilentlyContinue)) { return $false }
    try { & $Cli --version *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}
Write-Step "Installing or updating $Package via $manager from $releaseTag ..."
Invoke-ManagedInstall -Force
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Install failed; repairing with the same manager and interpreter ..."
    Remove-ManagedInstall
    Invoke-ManagedInstall
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-DeeprWorks)) {
    Write-Warn "$Cli did not run cleanly; attempting one clean reinstall via $manager ..."
    Remove-ManagedInstall
    Invoke-ManagedInstall
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-DeeprWorks)) {
    Write-Err "Install completed but '$Cli' still does not run. Check PATH or rerun this installer to repair via $manager."
    exit 1
}
& $Cli --version
$shownVersion = $true

Write-Host ""
Write-Ok "==> Done."
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
if (-not $shownVersion) { Write-Host "  0. Open a NEW terminal (so PATH picks up $Cli)" }
Write-Host "  1. $Cli init"
Write-Host "  2. $Cli doctor"
Write-Host "  3. Configure owned-local Ollama or a safety-eligible plan CLI"
Write-Host "  4. Keep the repository-wide ceiling at or below: $Cli budget set 5"
Write-Host ""
Write-Host "Quick start:"
Write-Host "  $Cli capacity"
Write-Host ""
Write-Host "Update later:  re-run this one-liner, or '$Cli upgrade'"
Write-Host "Uninstall:     re-run this one-liner with -Uninstall"
Write-Host ""
Write-Host "Dev / editable from source:"
Write-Host "  git clone https://github.com/blisspixel/deepr.git; cd deepr; uv tool install --python 3.15 --managed-python -e ."
Write-Host ""
