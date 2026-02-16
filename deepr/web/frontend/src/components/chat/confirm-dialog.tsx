import type { ConfirmRequest } from '@/types'
import { Button } from '@/components/ui/button'
import { AlertTriangle } from 'lucide-react'

interface ConfirmDialogProps {
  request: ConfirmRequest
  onApprove: () => void
  onDeny: () => void
}

export function ConfirmDialog({ request, onApprove, onDeny }: ConfirmDialogProps) {
  return (
    <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4 space-y-2 text-sm">
      <div className="flex items-center gap-2 text-yellow-600 dark:text-yellow-500 font-medium">
        <AlertTriangle className="w-4 h-4" />
        Approval Required
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">{request.tool_name}</span>
          {request.query && <> — {request.query.slice(0, 100)}</>}
        </p>
        <p>
          Estimated cost: <span className="font-mono">${request.estimated_cost.toFixed(2)}</span>
          {' · '}
          Budget remaining: <span className="font-mono">${request.budget_remaining.toFixed(2)}</span>
        </p>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <Button size="sm" onClick={onApprove} className="h-7 text-xs">
          Approve
        </Button>
        <Button size="sm" variant="outline" onClick={onDeny} className="h-7 text-xs">
          Deny
        </Button>
      </div>
    </div>
  )
}
