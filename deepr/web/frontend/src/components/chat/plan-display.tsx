import { cn } from '@/lib/utils'
import type { PlanStep } from '@/types'
import { CheckCircle, Circle, Loader2, XCircle } from 'lucide-react'

interface PlanDisplayProps {
  query: string
  steps: PlanStep[]
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  pending: <Circle className="w-3.5 h-3.5 text-muted-foreground" />,
  running: <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />,
  done: <CheckCircle className="w-3.5 h-3.5 text-green-600" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-600" />,
}

export function PlanDisplay({ query, steps }: PlanDisplayProps) {
  if (steps.length === 0) return null

  return (
    <div className="rounded-lg border bg-muted/30 p-4 space-y-2 text-sm">
      <div className="text-xs font-medium text-muted-foreground">Plan: {query.slice(0, 120)}</div>
      <ol className="space-y-1.5">
        {steps.map((step) => (
          <li key={step.id} className="flex items-start gap-2">
            <span className="flex-shrink-0 mt-0.5">{STATUS_ICON[step.status] || STATUS_ICON.pending}</span>
            <div className="flex-1 min-w-0">
              <span className={cn(
                'text-xs',
                step.status === 'done' ? 'text-foreground' :
                step.status === 'failed' ? 'text-red-600 line-through' :
                step.status === 'running' ? 'text-foreground font-medium' :
                'text-muted-foreground'
              )}>
                {step.id}. {step.title}
              </span>
              {step.result && step.status === 'done' && (
                <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">{step.result}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
