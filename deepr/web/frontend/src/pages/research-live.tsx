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
import { DetailSkeleton } from '@/components/ui/skeleton'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

export default function ResearchLive() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [elapsed, setElapsed] = useState(0)

  const { data: job, isLoading, isError, refetch } = useQuery({
    queryKey: ['jobs', id],
    queryFn: () => jobsApi.get(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return (status === 'completed' || status === 'failed') ? false : 3000
    },
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

  if (isLoading) return <DetailSkeleton />

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

  // If completed, show summary with details
  if (job.status === 'completed') {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-6 animate-fade-in">
        {/* Back nav */}
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        {/* Success banner */}
        <div className="rounded-lg border bg-card p-6 space-y-4">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 bg-success/10 rounded-full flex items-center justify-center flex-shrink-0">
              <Zap className="w-5 h-5 text-success" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold text-foreground">Research Complete</h2>
              <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{job.prompt}</p>
            </div>
            <button
              onClick={() => navigate(`/results/${job.id}`)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 flex-shrink-0"
            >
              View Result
              <ExternalLink className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="rounded-lg border bg-card p-4 space-y-1">
            <p className="text-xs text-muted-foreground flex items-center gap-1.5"><DollarSign className="w-3 h-3" />Cost</p>
            <p className="text-lg font-semibold text-foreground">{formatCurrency(job.cost)}</p>
          </div>
          <div className="rounded-lg border bg-card p-4 space-y-1">
            <p className="text-xs text-muted-foreground flex items-center gap-1.5"><Hash className="w-3 h-3" />Tokens</p>
            <p className="text-lg font-semibold text-foreground">{(job.tokens_used || 0).toLocaleString()}</p>
          </div>
          <div className="rounded-lg border bg-card p-4 space-y-1">
            <p className="text-xs text-muted-foreground flex items-center gap-1.5"><Clock className="w-3 h-3" />Completed</p>
            <p className="text-sm font-semibold text-foreground mt-1">{job.completed_at ? new Date(job.completed_at).toLocaleDateString() : 'N/A'}</p>
          </div>
          <div className="rounded-lg border bg-card p-4 space-y-1">
            <p className="text-xs text-muted-foreground">Model</p>
            <p className="text-sm font-medium text-foreground mt-1">{job.model}</p>
          </div>
        </div>

        {/* Result preview */}
        {job.result && (
          <div className="rounded-lg border bg-card p-5 space-y-3">
            <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">Preview</h3>
            <p className="text-sm text-muted-foreground line-clamp-4 whitespace-pre-line">
              {job.result
                .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
                .replace(/https?:\/\/\S+/g, '')
                .replace(/[#*`]/g, '')
                .replace(/\s+/g, ' ')
                .trim()
                .substring(0, 400)}
            </p>
            <button
              onClick={() => navigate(`/results/${job.id}`)}
              className="text-sm text-primary hover:underline font-medium"
            >
              Read full result →
            </button>
          </div>
        )}
      </div>
    )
  }

  const isActive = ['queued', 'processing'].includes(job.status)

  // Determine phases based on actual job status
  const phases: Phase[] = [
    { name: 'Queued', status: job.started_at ? 'completed' : 'active' },
    { name: 'Processing', status: job.status === 'processing' ? 'active' : 'pending' },
    { name: 'Complete', status: 'pending' },
  ]

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6 animate-fade-in">
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
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
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
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Cancel this research job?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will stop the job immediately. Any partial results will be lost and cannot be recovered.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep Running</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => cancelMutation.mutate()}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Cancel Job
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  )
}
