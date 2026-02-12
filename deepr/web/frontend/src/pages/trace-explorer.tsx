import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { cn, formatCurrency, formatDuration } from '@/lib/utils'
import { WaterfallChart } from '@/components/charts/waterfall'
import { TemporalTimeline } from '@/components/charts/timeline'
import apiClient from '@/api/client'
import {
  AlertTriangle,
  ArrowLeft,
  Clock,
  DollarSign,
  Hash,
  Loader2,
  Zap,
} from 'lucide-react'

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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center space-y-3">
        <AlertTriangle className="w-8 h-8 text-destructive" />
        <p className="text-base font-medium text-foreground">Failed to load trace data</p>
        <p className="text-sm text-muted-foreground">There was an error fetching the trace. Please try again.</p>
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

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

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
  )
}
