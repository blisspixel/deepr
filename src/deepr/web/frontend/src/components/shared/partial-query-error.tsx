import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

type PartialQueryErrorProps = {
  title: string
  description: string
  onRetry: () => void
  retrying?: boolean
}

export default function PartialQueryError({
  title,
  description,
  onRetry,
  retrying = false,
}: PartialQueryErrorProps) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/30 bg-warning/5 px-4 py-3">
      <AlertTriangle className="h-4 w-4 flex-shrink-0 text-warning" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={onRetry} loading={retrying}>
        Retry
      </Button>
    </div>
  )
}
