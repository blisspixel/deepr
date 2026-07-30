
# Fail-closed compatibility stub. The removed manager.py target cannot provide
# durable provider reconciliation or cost settlement.
Write-Error "BLOCKED: obsolete bulk cancellation cannot prove provider settlement. Use the provider console for manual reconciliation."
exit 2
