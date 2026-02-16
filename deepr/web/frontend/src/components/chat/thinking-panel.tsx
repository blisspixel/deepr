import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { ThoughtItem } from '@/types'
import { Brain, ChevronDown, ChevronUp } from 'lucide-react'

interface ThinkingPanelProps {
  thoughts: ThoughtItem[]
  isStreaming: boolean
}

const THOUGHT_ICONS: Record<string, string> = {
  plan_step: '\u{1F4CB}',
  tool_call: '\u{1F527}',
  evidence_found: '\u{1F4C4}',
  confidence: '\u{2705}',
  decision: '\u{2705}',
  search: '\u{1F50D}',
  synthesis: '\u{2728}',
  error: '\u{274C}',
}

function confidenceColor(c: number | null): string {
  if (c == null) return 'text-muted-foreground'
  if (c >= 0.8) return 'text-green-600'
  if (c >= 0.5) return 'text-yellow-600'
  return 'text-red-600'
}

export function ThinkingPanel({ thoughts, isStreaming }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(false)

  if (thoughts.length === 0) return null

  const showExpanded = isStreaming || expanded

  // Calculate thinking duration
  const first = thoughts[0]
  const last = thoughts[thoughts.length - 1]
  const durationMs =
    first && last
      ? new Date(last.timestamp).getTime() - new Date(first.timestamp).getTime()
      : 0
  const durationStr = durationMs > 0 ? `${(durationMs / 1000).toFixed(1)}s` : '<1s'

  return (
    <div className="rounded-lg border bg-muted/30 text-sm mb-2 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted/50 transition-colors"
      >
        <Brain className={cn('w-3.5 h-3.5', isStreaming ? 'text-primary animate-pulse' : 'text-muted-foreground')} />
        <span className="text-xs font-medium text-foreground">
          {isStreaming ? 'Thinking...' : `Thought for ${durationStr}`}
        </span>
        {!isStreaming && (
          <span className="text-[10px] text-muted-foreground">
            {thoughts.length} step{thoughts.length !== 1 ? 's' : ''}
          </span>
        )}
        <span className="ml-auto">
          {showExpanded ? (
            <ChevronUp className="w-3 h-3 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-3 h-3 text-muted-foreground" />
          )}
        </span>
      </button>

      {/* Thought list */}
      {showExpanded && (
        <div className="px-3 pb-2 space-y-1">
          {thoughts.map((t, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="flex-shrink-0 mt-0.5">{THOUGHT_ICONS[t.type] || '\u{25CF}'}</span>
              <span className="text-muted-foreground flex-1">{t.text}</span>
              {t.confidence != null && (
                <span className={cn('tabular-nums text-[10px] flex-shrink-0', confidenceColor(t.confidence))}>
                  {Math.round(t.confidence * 100)}%
                </span>
              )}
            </div>
          ))}
          {isStreaming && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              <span>Processing...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
