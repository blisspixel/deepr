# PowerShell script to set all environment variables from .env file for current session
$envFile = "C:\Users\nicks\OneDrive\deepr\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^(.*?)=(.*)$") {
            $name = $matches[1]
            $value = $matches[2]
            Set-Item -Path "Env:$name" -Value $value
        }
    }
    Write-Host ".env variables loaded for this session."
    Write-Host "You can now run: deepr --research ..."
} else {
    Write-Host ".env file not found at $envFile"
}
