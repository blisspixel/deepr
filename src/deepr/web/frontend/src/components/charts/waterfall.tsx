import { cn } from '@/lib/utils'
import { formatDuration } from '@/lib/utils'

interface WaterfallSpan {
  id: string
  name: string
  start_ms: number
  end_ms: number
  duration_ms: number
  status: 'completed' | 'failed' | 'running'
  depth: number
  cost?: number
  tokens?: number
  model?: string
}

interface WaterfallChartProps {
  spans: WaterfallSpan[]
  totalDuration: number
  selectedSpanId?: string
  onSelectSpan?: (span: WaterfallSpan) => void
  className?: string
}

export function WaterfallChart({
  spans,
  totalDuration,
  selectedSpanId,
  onSelectSpan,
  className,
}: WaterfallChartProps) {
  const getBarStyle = (span: WaterfallSpan) => {
    const left = totalDuration > 0 ? (span.start_ms / totalDuration) * 100 : 0
    const width = totalDuration > 0 ? ((span.end_ms - span.start_ms) / totalDuration) * 100 : 0
    return { left: `${left}%`, width: `${Math.max(width, 0.5)}%` }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-primary'
      case 'failed': return 'bg-destructive'
      case 'running': return 'bg-info animate-pulse-slow'
      default: return 'bg-muted'
    }
  }

  // Time markers
  const markers = [0, 0.25, 0.5, 0.75, 1].map(pct => ({
    label: formatDuration(Math.round((totalDuration * pct) / 1000)),
    position: `${pct * 100}%`,
  }))

  return (
    <div className={cn('space-y-1', className)}>
      {/* Time axis */}
      <div className="relative h-6 border-b border-border ml-32">
        {markers.map((marker) => (
          <span
            key={marker.label}
            className="absolute text-[10px] text-muted-foreground -translate-x-1/2"
            style={{ left: marker.position }}
          >
            {marker.label}
          </span>
        ))}
      </div>

      {/* Spans */}
      {spans.map((span) => (
        <div
          key={span.id}
          className={cn(
            'flex items-center h-7 cursor-pointer hover:bg-accent/50 rounded transition-colors group',
            selectedSpanId === span.id && 'bg-accent'
          )}
          onClick={() => onSelectSpan?.(span)}
        >
          {/* Span name */}
          <div
            className="w-32 flex-shrink-0 text-xs truncate pr-2 text-muted-foreground group-hover:text-foreground"
            style={{ paddingLeft: `${span.depth * 12}px` }}
          >
            {span.depth > 0 && <span className="text-border mr-1">{'└'}</span>}
            {span.name}
          </div>

          {/* Bar */}
          <div className="relative flex-1 h-full">
            <div
              className={cn(
                'absolute top-1 h-5 rounded-sm transition-opacity',
                getStatusColor(span.status),
                selectedSpanId === span.id ? 'opacity-100' : 'opacity-75 group-hover:opacity-100'
              )}
              style={getBarStyle(span)}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
