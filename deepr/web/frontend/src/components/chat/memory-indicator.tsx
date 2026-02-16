import { useState } from 'react'
import type { MemoryContext } from '@/types'
import { Brain, ChevronDown, ChevronUp } from 'lucide-react'

interface MemoryIndicatorProps {
  memory: MemoryContext
}

export function MemoryIndicator({ memory }: MemoryIndicatorProps) {
  const [expanded, setExpanded] = useState(false)

  if (memory.conversations === 0 && memory.domains.length === 0) return null

  return (
    <div className="px-4 py-1.5 border-b bg-muted/20 text-[11px] text-muted-foreground">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 w-full text-left hover:text-foreground transition-colors"
      >
        <Brain className="w-3 h-3" />
        <span>
          {memory.conversations} past conversation{memory.conversations !== 1 ? 's' : ''}
          {memory.domains.length > 0 && (
            <>
              {' · Knows: '}
              {memory.domains
                .slice(0, 3)
                .map((d) => `${d.name} (${Math.round(d.confidence * 100)}%)`)
                .join(', ')}
            </>
          )}
          {memory.gaps > 0 && <> · {memory.gaps} gap{memory.gaps !== 1 ? 's' : ''}</>}
        </span>
        {expanded ? <ChevronUp className="w-3 h-3 ml-auto" /> : <ChevronDown className="w-3 h-3 ml-auto" />}
      </button>
      {expanded && (
        <div className="mt-1.5 space-y-1 pl-5">
          {memory.domains.map((d) => (
            <div key={d.name} className="flex items-center gap-2">
              <div className="w-16 h-1 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full"
                  style={{ width: `${Math.round(d.confidence * 100)}%` }}
                />
              </div>
              <span>{d.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
