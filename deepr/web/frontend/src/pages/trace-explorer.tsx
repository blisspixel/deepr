import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cn, formatCurrency, formatDuration, formatRelativeTime } from '@/lib/utils'
import { WaterfallChart } from '@/components/charts/waterfall'
import { TemporalTimeline } from '@/components/charts/timeline'
import apiClient from '@/api/client'
import type { DecisionRecord } from '@/types'
import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  Clock,
  DollarSign,
  GitBranch,
  Hash,
  PanelRightClose,
  PanelRightOpen,
  Zap,
} from 'lucide-react'
import { DetailSkeleton } from '@/components/ui/skeleton'

interface SpanData {
  id: string
  name: string
  parent_id?: string
  start_ms: number
  end_ms: number
  duration_ms: number
  status: 'completed' | 'failed' | 'running'
  cost: number
  tokens: number
  model?: string
  sources_count?: number
  findings_count?: number
}

interface FindingData {
  timestamp_ms: number
  type: 'fact' | 'hypothesis' | 'contradiction'
  content: string
  confidence: number
  confidence_change?: 'up' | 'down'
}

export default function TraceExplorer() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [selectedSpan, setSelectedSpan] = useState<SpanData | null>(null)
  const [decisionPanelOpen, setDecisionPanelOpen] = useState(false)
  const [expandedDecision, setExpandedDecision] = useState<string | null>(null)

  const { data: traceData, isLoading, isError } = useQuery({
    queryKey: ['traces', id],
    queryFn: async () => {
      const response = await apiClient.get(`/traces/${id}`)
      return response.data.trace as {
        job_id: string
        spans: SpanData[]
        total_duration_ms: number
        total_cost: number
        total_tokens: number
        prompt: string
        model: string
        expert_name?: string
      }
    },
    enabled: !!id,
  })

  const { data: findingsData } = useQuery({
    queryKey: ['traces', id, 'temporal'],
    queryFn: async () => {
      try {
        const response = await apiClient.get(`/traces/${id}/temporal`)
        return response.data.findings as FindingData[]
      } catch {
        return [] as FindingData[]
      }
    },
    enabled: !!id,
  })

  const { data: decisionsData } = useQuery({
    queryKey: ['traces', id, 'decisions', traceData?.expert_name, traceData?.job_id],
    queryFn: async () => {
      if (!traceData?.expert_name || !traceData?.job_id) return [] as DecisionRecord[]
      try {
        const name = encodeURIComponent(traceData.expert_name)
        const response = await apiClient.get(`/experts/${name}/decisions`, {
          params: { job_id: traceData.job_id },
        })
        return (response.data.decisions || []) as DecisionRecord[]
      } catch {
        return [] as DecisionRecord[]
      }
    },
    enabled: !!traceData?.expert_name && !!traceData?.job_id,
  })

  if (isLoading) return <DetailSkeleton />

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center space-y-3">
        <AlertTriangle className="w-8 h-8 text-muted-foreground/40" />
        <p className="text-base font-medium text-foreground">Unable to load trace</p>
        <p className="text-sm text-muted-foreground">Could not connect to the backend. Trace data will appear here once the server is running.</p>
        <button
          onClick={() => navigate(-1)}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
        >
          Go Back
        </button>
      </div>
    )
  }

  // Flatten spans for waterfall (add depth info)
  const flattenSpans = (spans: SpanData[]): (SpanData & { depth: number })[] => {
    const result: (SpanData & { depth: number })[] = []
    const byParent = new Map<string | undefined, SpanData[]>()
    spans.forEach(s => {
      const key = s.parent_id || '__root__'
      if (!byParent.has(key)) byParent.set(key, [])
      byParent.get(key)!.push(s)
    })

    const walk = (parentId: string | undefined, depth: number) => {
      const key = parentId || '__root__'
      const children = byParent.get(key) || []
      children.sort((a, b) => a.start_ms - b.start_ms)
      children.forEach(child => {
        result.push({ ...child, depth })
        walk(child.id, depth + 1)
      })
    }
    walk(undefined, 0)
    return result
  }

  const waterfallSpans = traceData ? flattenSpans(traceData.spans) : []
  const hasDecisions = decisionsData && decisionsData.length > 0

  return (
    <div className="flex animate-fade-in">
      {/* Main content */}
      <div className={cn('flex-1 p-6 space-y-6', decisionPanelOpen && hasDecisions && 'pr-3')}>
        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <button
              onClick={() => navigate(-1)}
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            {hasDecisions && (
              <button
                onClick={() => setDecisionPanelOpen(prev => !prev)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary text-muted-foreground hover:text-foreground transition-colors"
              >
                {decisionPanelOpen ? <PanelRightClose className="w-3.5 h-3.5" /> : <PanelRightOpen className="w-3.5 h-3.5" />}
                Decisions ({decisionsData.length})
              </button>
            )}
          </div>

          <h1 className="text-xl font-semibold text-foreground">
            Trace Explorer
          </h1>

          {traceData && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {formatDuration(Math.round(traceData.total_duration_ms / 1000))}
              </span>
              <span className="inline-flex items-center gap-1">
                <DollarSign className="w-3.5 h-3.5" />
                {formatCurrency(traceData.total_cost)}
              </span>
              <span className="inline-flex items-center gap-1">
                <Hash className="w-3.5 h-3.5" />
                {traceData.total_tokens.toLocaleString()} tokens
              </span>
              <span className="px-2 py-0.5 bg-secondary rounded text-xs font-medium">{traceData.model}</span>
            </div>
          )}
        </div>

        {!traceData ? (
          <div className="rounded-lg border bg-card p-12 text-center space-y-3">
            <Zap className="w-8 h-8 text-muted-foreground/40 mx-auto" />
            <p className="text-base font-medium text-foreground">No trace data available</p>
            <p className="text-sm text-muted-foreground">
              Trace data is generated during research execution. Check back after the job completes.
            </p>
            <button
              onClick={() => navigate(`/results/${id}`)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium mt-2 hover:bg-primary/90"
            >
              View Result
            </button>
          </div>
        ) : (
          <>
            {/* Waterfall */}
            <div className="rounded-lg border bg-card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Waterfall</h2>
              <WaterfallChart
                spans={waterfallSpans}
                totalDuration={traceData.total_duration_ms}
                selectedSpanId={selectedSpan?.id}
                onSelectSpan={(span) => {
                  const s = traceData.spans.find(sp => sp.id === span.id)
                  setSelectedSpan(s || null)
                }}
              />
            </div>

            {/* Selected Span Detail */}
            {selectedSpan && (
              <div className="rounded-lg border bg-card p-5 space-y-3 animate-fade-in">
                <h3 className="text-sm font-semibold text-foreground">
                  Span: {selectedSpan.name}
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-muted-foreground">Duration</p>
                    <p className="font-medium text-foreground">{formatDuration(Math.round(selectedSpan.duration_ms / 1000))}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Cost</p>
                    <p className="font-medium text-foreground">{formatCurrency(selectedSpan.cost)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Tokens</p>
                    <p className="font-medium text-foreground">{selectedSpan.tokens.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Status</p>
                    <p className={cn(
                      'font-medium capitalize',
                      selectedSpan.status === 'completed' && 'text-success',
                      selectedSpan.status === 'failed' && 'text-destructive',
                      selectedSpan.status === 'running' && 'text-info'
                    )}>
                      {selectedSpan.status}
                    </p>
                  </div>
                </div>
                {selectedSpan.model && (
                  <p className="text-xs text-muted-foreground">Model: {selectedSpan.model}</p>
                )}
                {selectedSpan.sources_count !== undefined && (
                  <p className="text-xs text-muted-foreground">Sources consulted: {selectedSpan.sources_count}</p>
                )}
                {selectedSpan.findings_count !== undefined && (
                  <p className="text-xs text-muted-foreground">Findings extracted: {selectedSpan.findings_count}</p>
                )}
              </div>
            )}

            {/* Temporal Findings */}
            {findingsData && findingsData.length > 0 && (
              <div className="rounded-lg border bg-card p-5 space-y-4">
                <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">
                  Temporal Findings
                </h2>
                <TemporalTimeline
                  events={findingsData}
                  totalDuration={traceData.total_duration_ms}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* Decision Sidebar */}
      {decisionPanelOpen && hasDecisions && (
        <div className="w-80 flex-shrink-0 border-l bg-card p-4 space-y-3 overflow-auto h-[calc(100vh-4rem)]">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider flex items-center gap-2">
            <GitBranch className="w-3.5 h-3.5" />
            Decisions
          </h2>
          <div className="space-y-2">
            {decisionsData.map((dec) => {
              const isExpanded = expandedDecision === dec.id
              return (
                <button
                  key={dec.id}
                  onClick={() => setExpandedDecision(isExpanded ? null : dec.id)}
                  className="w-full text-left rounded-lg border p-3 space-y-1 hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 rounded bg-secondary text-[10px] font-medium text-muted-foreground">
                      {dec.decision_type}
                    </span>
                    <ChevronRight className={cn('w-3 h-3 text-muted-foreground transition-transform ml-auto', isExpanded && 'rotate-90')} />
                  </div>
                  <p className="text-xs font-medium text-foreground">{dec.title}</p>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span>{Math.round(dec.confidence * 100)}%</span>
                    <span>{formatRelativeTime(dec.timestamp)}</span>
                  </div>
                  {isExpanded && (
                    <div className="pt-2 space-y-1 border-t mt-2">
                      <p className="text-xs text-muted-foreground">{dec.rationale}</p>
                      {dec.cost_impact !== 0 && (
                        <p className="text-[10px] text-muted-foreground">Cost impact: {formatCurrency(Math.abs(dec.cost_impact))}</p>
                      )}
                      {dec.alternatives.length > 0 && (
                        <p className="text-[10px] text-muted-foreground">
                          Alternatives: {dec.alternatives.join(', ')}
                        </p>
                      )}
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
