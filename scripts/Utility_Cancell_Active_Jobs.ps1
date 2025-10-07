
# PowerShell script to cancel all active jobs using manager.py and notify if none found
$output = python manager.py --cancel-all
Write-Output $output
if ($output -match "0 active") {
	Write-Host "No active jobs found to cancel." -ForegroundColor Yellow
}
Start-Sleep -Seconds 20
