# Easy one-line installer for deepr (Windows PowerShell)
# Usage (recommended):
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/blisspixel/deepr/main/scripts/install.ps1 | iex"

$ErrorActionPreference = "Stop"

$Package = "deepr-research"
$Cli = "deepr"

Write-Host "==> Installing $Package (CLI: $Cli) ..." -ForegroundColor Cyan
Write-Host ""

$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    $python = "py"
}
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python 3.12+ is required." -ForegroundColor Red
    exit 1
}

$ver = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
if (-not $ver -or ([version]$ver -lt [version]"3.12")) {
    Write-Host "Error: Python 3.12+ is required (found $ver)." -ForegroundColor Red
    exit 1
}

if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Host "==> pipx not found. Installing pipx..." -ForegroundColor Yellow
    & $python -m pip install --user pipx --quiet
    & $python -m pipx ensurepath
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" + [System.Environment]::GetEnvironmentVariable("Path","Machine")
}

Write-Host "==> Using pipx to install $Package ..." -ForegroundColor Green
pipx install $Package

Write-Host ""
Write-Host "==> Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open a NEW terminal"
Write-Host "  2. Run: $Cli doctor"
Write-Host "  3. Copy .env.example to .env and add at least one API key (XAI/Gemini/OpenAI/Anthropic)"
Write-Host "  4. $Cli budget set 50"
Write-Host ""
Write-Host "Quick start:"
Write-Host "  $Cli research `"your question`" --auto"
Write-Host ""
Write-Host "Note: deepr has powerful optional features (web dashboard, full extras)."
Write-Host "      See README for pipx install deepr-research[web] etc. (advanced users)."
Write-Host ""
Write-Host "For development / editable from source (see existing scripts/ for advanced setup):"
Write-Host "  git clone https://github.com/blisspixel/deepr.git"
Write-Host "  cd deepr/deepr"
Write-Host "  pipx install -e ."
Write-Host ""