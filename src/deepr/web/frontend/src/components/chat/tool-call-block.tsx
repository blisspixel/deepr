import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { CheckCircle, ChevronRight, Loader2, Search, Globe, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

const TOOL_LABELS: Record<string, { label: string; icon: typeof Search }> = {
  search_knowledge_base: { label: 'Searched knowledge base', icon: Search },
  standard_research: { label: 'Searched the web', icon: Globe },
  deep_research: { label: 'Ran deep research', icon: Sparkles },
}

interface ToolCallBlockProps {
  tool: string
  query?: string
  elapsed_ms?: number
  running?: boolean
}

export function ToolCallBlock({ tool, query, elapsed_ms, running }: ToolCallBlockProps) {
  const info = TOOL_LABELS[tool] || { label: tool, icon: Search }
  const Icon = info.icon

  return (
    <Collapsible defaultOpen={running}>
      <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors py-1 group w-full">
        {running ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-primary flex-shrink-0" />
        ) : (
          <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
        )}
        <Icon className="w-3 h-3 flex-shrink-0" />
        <span>{running ? info.label.replace(/^(Searched|Ran)/, (m) => m === 'Searched' ? 'Searching' : 'Running') : info.label}</span>
        {elapsed_ms != null && (
          <span className="tabular-nums">{elapsed_ms < 1000 ? `${elapsed_ms}ms` : `${(elapsed_ms / 1000).toFixed(1)}s`}</span>
        )}
        <ChevronRight className={cn(
          'w-3 h-3 ml-auto transition-transform',
          'group-data-[state=open]:rotate-90',
        )} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        {query && (
          <div className="ml-6 pl-2 border-l text-[11px] text-muted-foreground py-1 break-words">
            {query}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
