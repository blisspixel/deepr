# Install deepr CLI globally so it can be used anywhere (PowerShell)

Write-Host "Installing deepr CLI..." -ForegroundColor Cyan
Write-Host ""

# Check Python version
try {
    $pythonVersion = (python --version 2>&1) -replace 'Python ', ''
    Write-Host "Python version: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python not found. Please install Python 3.9+ first." -ForegroundColor Red
    exit 1
}

# Install in editable mode for development
Write-Host "Installing in editable mode..." -ForegroundColor Yellow
pip install -e .

if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation failed!" -ForegroundColor Red
    exit 1
}

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow

try {
    $null = Get-Command deepr -ErrorAction Stop
    Write-Host "✓ deepr command is available" -ForegroundColor Green
    deepr --version
} catch {
    Write-Host "✗ deepr command not found in PATH" -ForegroundColor Red
    Write-Host "  Try: pip install --user -e ." -ForegroundColor Yellow
    Write-Host "  And ensure Python Scripts directory is in your PATH" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Checking environment variables..." -ForegroundColor Yellow
$missing = $false
if (-not $env:OPENAI_API_KEY) {
    Write-Host "  WARNING: OPENAI_API_KEY not set (required for research)" -ForegroundColor Red
    $missing = $true
}
foreach ($key in @("XAI_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY")) {
    if ([Environment]::GetEnvironmentVariable($key)) {
        Write-Host "  $key set" -ForegroundColor Green
    }
}
if ($missing) {
    Write-Host "  Set required keys in .env or system environment" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installation complete! You can now use 'deepr' from anywhere." -ForegroundColor Green
Write-Host ""
Write-Host "Quick start:" -ForegroundColor Cyan
Write-Host "  deepr --help                   # Show all commands"
Write-Host "  deepr doctor                   # Check configuration"
Write-Host "  deepr expert list              # List experts"
Write-Host "  deepr research `"query`"         # Run research"
Write-Host ""
Write-Host "MCP server:" -ForegroundColor Cyan
Write-Host "  python -m deepr.mcp.server     # Start MCP server (stdio)"
Write-Host ""
