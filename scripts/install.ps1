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
Write-Host "Installation complete! You can now use 'deepr' from anywhere." -ForegroundColor Green
Write-Host ""
Write-Host "Quick start:" -ForegroundColor Cyan
Write-Host "  deepr --help                   # Show all commands"
Write-Host "  deepr expert list              # List experts"
Write-Host "  deepr expert chat <name>       # Chat with an expert"
Write-Host "  deepr run focus <query>        # Run quick research"
Write-Host ""
