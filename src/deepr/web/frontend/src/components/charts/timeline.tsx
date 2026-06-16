import { cn } from '@/lib/utils'
import { formatDuration } from '@/lib/utils'
import { ArrowUp, ArrowDown, AlertTriangle, Lightbulb, CheckCircle2 } from 'lucide-react'

interface TimelineEvent {
  timestamp_ms: number
  type: 'fact' | 'hypothesis' | 'contradiction'
  content: string
  confidence: number
  confidence_change?: 'up' | 'down'
}

interface TimelineProps {
  events: TimelineEvent[]
  totalDuration: number
  className?: string
}

export function TemporalTimeline({ events, className }: TimelineProps) {
  const getIcon = (type: string) => {
    switch (type) {
      case 'fact': return <CheckCircle2 className="w-3.5 h-3.5 text-success" />
      case 'hypothesis': return <Lightbulb className="w-3.5 h-3.5 text-warning" />
      case 'contradiction': return <AlertTriangle className="w-3.5 h-3.5 text-destructive" />
      default: return null
    }
  }

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'fact': return 'FACT'
      case 'hypothesis': return 'HYPOTHESIS'
      case 'contradiction': return 'CONTRADICTION'
      default: return type.toUpperCase()
    }
  }

  return (
    <div className={cn('space-y-2', className)}>
      {events.map((event, index) => (
        <div key={index} className="flex items-start gap-3 text-sm">
          {/* Timestamp */}
          <span className="text-xs text-muted-foreground w-12 flex-shrink-0 tabular-nums pt-0.5">
            {formatDuration(Math.round(event.timestamp_ms / 1000))}
          </span>

          {/* Icon */}
          <div className="flex-shrink-0 pt-0.5">
            {getIcon(event.type)}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <span className={cn(
              'text-[10px] font-semibold uppercase tracking-wider mr-2',
              event.type === 'fact' && 'text-success',
              event.type === 'hypothesis' && 'text-warning',
              event.type === 'contradiction' && 'text-destructive'
            )}>
              [{getTypeLabel(event.type)}]
            </span>
            {event.confidence_change && (
              <span className="inline-flex items-center mr-1">
                {event.confidence_change === 'up'
                  ? <ArrowUp className="w-3 h-3 text-success" />
                  : <ArrowDown className="w-3 h-3 text-destructive" />
                }
              </span>
            )}
            <span className="text-foreground">{event.content}</span>
            <span className="text-muted-foreground ml-1 text-xs">
              ({(event.confidence * 100).toFixed(0)}%)
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
