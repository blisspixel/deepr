import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { cn, formatCurrency, formatDuration } from '@/lib/utils'
import { ProgressPhases, type Phase } from '@/components/charts/progress-phases'
import {
  AlertTriangle,
  ArrowLeft,
  Clock,
  DollarSign,
  ExternalLink,
  Hash,
  Loader2,
  Square,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { wsClient } from '@/api/websocket'

export default function ResearchLive() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [elapsed, setElapsed] = useState(0)

  const { data: job, isLoading, isError, refetch } = useQuery({
    queryKey: ['jobs', id],
    queryFn: () => jobsApi.get(id!),
    enabled: !!id,
    refetchInterval: 3000,
  })

  // Subscribe to job-specific updates
  useEffect(() => {
    if (!id) return
    wsClient.subscribeToJobs(id)
    const cleanup = wsClient.on('job_updated', () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', id] })
    })
    return () => {
      wsClient.unsubscribeFromJobs(id)
      cleanup()
    }
  }, [id, queryClient])

  // Elapsed timer
  useEffect(() => {
    if (!job?.started_at || job.status === 'completed' || job.status === 'failed') return
    const start = new Date(job.started_at).getTime()
    setElapsed(Math.floor((Date.now() - start) / 1000))
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [job?.started_at, job?.status])

  const cancelMutation = useMutation({
    mutationFn: () => jobsApi.cancel(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      navigate('/')
    },
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
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <AlertTriangle className="w-10 h-10 text-destructive mb-3" />
        <p className="text-lg font-medium text-foreground mb-1">Failed to load job</p>
        <p className="text-sm text-muted-foreground mb-4">Something went wrong fetching this research job.</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center">
        <p className="text-lg font-medium text-foreground mb-2">Job not found</p>
        <p className="text-sm text-muted-foreground mb-4">This research job doesn't exist.</p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium"
        >
          Back to Overview
        </button>
      </div>
    )
  }

  // If completed, redirect to result
  if (job.status === 'completed') {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <div className="rounded-lg border bg-card p-8 text-center space-y-4">
          <div className="w-12 h-12 bg-success/10 rounded-full flex items-center justify-center mx-auto">
            <Zap className="w-6 h-6 text-success" />
          </div>
          <h2 className="text-xl font-semibold text-foreground">Research Complete</h2>
          <p className="text-sm text-muted-foreground">
            {formatCurrency(job.cost)} · {job.tokens_used?.toLocaleString() || 0} tokens
          </p>
          <button
            onClick={() => navigate(`/results/${job.id}`)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
          >
            View Result
            <ExternalLink className="w-4 h-4" />
          </button>
        </div>
      </div>
    )
  }

  const isActive = ['queued', 'processing'].includes(job.status)

  // Determine phases
  const phases: Phase[] = [
    { name: 'Queued', status: job.started_at ? 'completed' : job.status === 'queued' ? 'active' : 'pending' },
    { name: 'Init', status: job.status === 'processing' && elapsed < 10 ? 'active' : elapsed >= 10 ? 'completed' : 'pending' },
    { name: 'Searching', status: elapsed >= 10 && elapsed < 60 ? 'active' : elapsed >= 60 ? 'completed' : 'pending' },
    { name: 'Analyzing', status: elapsed >= 60 && elapsed < 180 ? 'active' : elapsed >= 180 ? 'completed' : 'pending' },
    { name: 'Synthesizing', status: elapsed >= 180 && elapsed < 240 ? 'active' : elapsed >= 240 ? 'completed' : 'pending' },
    { name: 'Finalizing', status: elapsed >= 240 ? 'active' : 'pending' },
  ]

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <h1 className="text-xl font-semibold text-foreground line-clamp-2">
          {job.prompt.substring(0, 120)}{job.prompt.length > 120 ? '...' : ''}
        </h1>
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span className={cn(
            'inline-flex items-center gap-1.5',
            isActive && 'text-info'
          )}>
            {isActive && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {job.status === 'failed' && <Square className="w-3.5 h-3.5 text-destructive" />}
            {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
          </span>
          <span className="text-border">·</span>
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {formatDuration(elapsed)}
          </span>
          <span className="text-border">·</span>
          <span>{job.model}</span>
        </div>
      </div>

      {/* Progress Timeline */}
      {isActive && (
        <div className="rounded-lg border bg-card p-6">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider mb-4">Progress</h2>
          <ProgressPhases phases={phases} />
        </div>
      )}

      {/* Failed state */}
      {job.status === 'failed' && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
          <h2 className="text-sm font-semibold text-destructive mb-2">Research Failed</h2>
          <p className="text-sm text-foreground">{job.last_error || 'An unknown error occurred'}</p>
        </div>
      )}

      {/* Live Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-lg border bg-card p-4 space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Hash className="w-3 h-3" />
            Tokens
          </div>
          <p className="text-lg font-semibold text-foreground tabular-nums">
            {(job.tokens_used || 0).toLocaleString()}
          </p>
          <div className="w-full h-1 bg-secondary rounded-full overflow-hidden">
            <div className="h-full bg-primary rounded-full" style={{ width: `${Math.min((job.tokens_used || 0) / 50000 * 100, 100)}%` }} />
          </div>
        </div>

        <div className="rounded-lg border bg-card p-4 space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <DollarSign className="w-3 h-3" />
            Cost
          </div>
          <p className="text-lg font-semibold text-foreground tabular-nums">
            {formatCurrency(job.cost || 0)}
          </p>
          <div className="w-full h-1 bg-secondary rounded-full overflow-hidden">
            <div className="h-full bg-warning rounded-full" style={{ width: `${Math.min((job.cost || 0) / 5 * 100, 100)}%` }} />
          </div>
        </div>

        <div className="rounded-lg border bg-card p-4 space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="w-3 h-3" />
            Elapsed
          </div>
          <p className="text-lg font-semibold text-foreground tabular-nums">
            {formatDuration(elapsed)}
          </p>
          <p className="text-xs text-muted-foreground">
            Started {job.started_at ? new Date(job.started_at).toLocaleTimeString() : 'N/A'}
          </p>
        </div>
      </div>

      {/* Actions */}
      {isActive && (
        <div className="flex justify-center gap-3">
          <button
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 border rounded-lg text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
          >
            {cancelMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Square className="w-4 h-4" />
            )}
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}
