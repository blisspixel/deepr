import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { formatCurrency, formatRelativeTime } from '@/lib/utils'
import { cn } from '@/lib/utils'
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  DollarSign,
  Loader2,
  Plus,
  Search,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react'
import { Sparkline } from '@/components/charts/sparkline'

export default function Overview() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const cleanupMutation = useMutation({
    mutationFn: () => jobsApi.cleanupStale(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const { data: jobsData } = useQuery({
    queryKey: ['jobs', 'recent'],
    queryFn: () => jobsApi.list({ limit: 10 }),
    refetchInterval: 5000,
  })

  const { data: jobStats } = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: () => jobsApi.getStats(),
    refetchInterval: 10000,
  })

  const { data: costSummary } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 10000,
  })

  const { data: trends } = useQuery({
    queryKey: ['cost', 'trends', 14],
    queryFn: () => costApi.getTrends(14),
  })

  const jobs = jobsData?.jobs || []
  const liveJobs = jobs.filter(j => ['queued', 'processing'].includes(j.status))
  const completedCount = jobStats?.completed ?? jobs.filter(j => j.status === 'completed').length
  const failedCount = jobStats?.failed ?? jobs.filter(j => j.status === 'failed').length
  const dailyUtilization = costSummary && costSummary.daily_limit > 0
    ? (costSummary.daily / costSummary.daily_limit) * 100
    : 0

  const trendData = trends?.daily?.map((t: { cost: number }) => ({ value: t.cost })) || []

  const quickActions = [
    { label: 'New Research', icon: Plus, onClick: () => navigate('/research'), variant: 'primary' as const },
    { label: 'View Results', icon: Search, onClick: () => navigate('/results'), variant: 'secondary' as const },
    { label: 'Ask Expert', icon: Users, onClick: () => navigate('/experts'), variant: 'secondary' as const },
    { label: 'Check Costs', icon: DollarSign, onClick: () => navigate('/costs'), variant: 'secondary' as const },
  ]

  return (
    <div className="space-y-6 p-6 animate-fade-in">
      {/* Greeting + CTA */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Overview</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Research operations at a glance</p>
        </div>
        <button
          onClick={() => navigate('/research')}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Research
        </button>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Live Jobs */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <div className="flex items-center gap-2">
            {liveJobs.length > 0 && <span className="w-2 h-2 rounded-full bg-info animate-pulse" />}
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Live Jobs</p>
          </div>
          <p className="text-3xl font-semibold text-foreground tabular-nums">{liveJobs.length}</p>
          <p className="text-xs text-muted-foreground">
            {liveJobs.length > 0 ? 'Processing now' : 'No active jobs'}
          </p>
        </div>

        {/* Completed */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Completed</p>
          </div>
          <p className="text-3xl font-semibold text-foreground tabular-nums">{completedCount}</p>
          <p className="text-xs text-muted-foreground">All time</p>
        </div>

        {/* Failed */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <div className="flex items-center gap-2">
            <XCircle className="w-3.5 h-3.5 text-destructive" />
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Failed</p>
          </div>
          <p className="text-3xl font-semibold text-foreground tabular-nums">{failedCount}</p>
          <p className="text-xs text-muted-foreground">All time</p>
        </div>

        {/* Daily Spend */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <div className="flex items-center gap-2">
            <DollarSign className="w-3.5 h-3.5 text-muted-foreground" />
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Today</p>
          </div>
          <p className="text-3xl font-semibold text-foreground tabular-nums">
            {formatCurrency(costSummary?.daily || 0)}
          </p>
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{formatCurrency(costSummary?.daily_limit || 100)} limit</span>
              <span>{dailyUtilization.toFixed(0)}%</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  dailyUtilization > 90 ? 'bg-destructive' :
                  dailyUtilization > 70 ? 'bg-warning' : 'bg-success'
                )}
                style={{ width: `${Math.min(dailyUtilization, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Jobs + Activity */}
        <div className="lg:col-span-2 space-y-6">
          {/* Live Jobs */}
          {liveJobs.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Live Jobs</h2>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => cleanupMutation.mutate()}
                    disabled={cleanupMutation.isPending}
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                  >
                    {cleanupMutation.isPending ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Trash2 className="w-3 h-3" />
                    )}
                    Clean up stale
                  </button>
                  <span className="flex items-center gap-1.5 text-xs text-info">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {liveJobs.length} running
                  </span>
                </div>
              </div>
              <div className="space-y-2">
                {liveJobs.map((job) => (
                  <div
                    key={job.id}
                    className="rounded-lg border bg-card p-4 cursor-pointer hover:border-primary/30 hover:shadow-md transition-all"
                    onClick={() => navigate(`/research/${job.id}`)}
                  >
                    <div className="flex justify-between items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {job.prompt.substring(0, 80)}{job.prompt.length > 80 ? '...' : ''}
                        </p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-xs text-muted-foreground">{job.model}</span>
                          <span className="text-border">·</span>
                          <span className="inline-flex items-center gap-1 text-xs text-info">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            {job.status === 'processing' ? 'Analyzing' : 'Queued'}
                          </span>
                        </div>
                      </div>
                      {job.cost > 0 && (
                        <span className="text-sm font-medium text-muted-foreground tabular-nums">
                          ~{formatCurrency(job.cost)}
                        </span>
                      )}
                    </div>
                    {/* Progress bar */}
                    <div className="mt-3 w-full h-1 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-primary/60 rounded-full animate-pulse w-full" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Activity */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Recent Activity</h2>
              <button
                onClick={() => navigate('/results')}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1"
              >
                View all <ArrowRight className="w-3 h-3" />
              </button>
            </div>
            <div className="rounded-lg border bg-card divide-y">
              {jobs.length === 0 ? (
                <div className="p-8 space-y-4">
                  <p className="text-sm font-medium text-foreground text-center mb-4">Get started in 3 steps</p>
                  <div className="space-y-3 max-w-sm mx-auto">
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">1</span>
                      <div>
                        <p className="text-sm text-foreground">Set a budget</p>
                        <p className="text-xs text-muted-foreground">
                          Run <code className="px-1 py-0.5 bg-muted rounded text-[11px]">deepr budget set 5</code> to cap spending at $5
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">2</span>
                      <div>
                        <p className="text-sm text-foreground">Run a research job</p>
                        <p className="text-xs text-muted-foreground">
                          Use the <button onClick={() => navigate('/research')} className="text-primary hover:underline">Research Studio</button> or CLI to submit a query
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">3</span>
                      <div>
                        <p className="text-sm text-foreground">Review results with citations</p>
                        <p className="text-xs text-muted-foreground">
                          Completed reports appear in <button onClick={() => navigate('/results')} className="text-primary hover:underline">Results</button> with full source attribution
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                jobs.slice(0, 8).map((job) => (
                  <div
                    key={job.id}
                    className="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => {
                      if (job.status === 'completed') navigate(`/results/${job.id}`)
                      else if (['queued', 'processing'].includes(job.status)) navigate(`/research/${job.id}`)
                      else navigate(`/results/${job.id}`)
                    }}
                  >
                    <div className="flex-shrink-0">
                      {job.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-success" />}
                      {job.status === 'processing' && <Loader2 className="w-4 h-4 text-info animate-spin" />}
                      {job.status === 'queued' && <Activity className="w-4 h-4 text-warning" />}
                      {job.status === 'failed' && <XCircle className="w-4 h-4 text-destructive" />}
                      {job.status === 'cancelled' && <XCircle className="w-4 h-4 text-muted-foreground" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground truncate">
                        {job.prompt.substring(0, 60)}{job.prompt.length > 60 ? '...' : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {job.cost > 0 && (
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {formatCurrency(job.cost)}
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {job.submitted_at && formatRelativeTime(job.submitted_at)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Cost Sparkline */}
          <div className="rounded-lg border bg-card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Cost Trend</h2>
            <Sparkline data={trendData} height={60} />
            <p className="text-xs text-muted-foreground">Last 14 days</p>
          </div>

          {/* Quick Actions */}
          <div className="rounded-lg border bg-card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Quick Actions</h2>
            <div className="grid grid-cols-2 gap-2">
              {quickActions.map((action) => (
                <button
                  key={action.label}
                  onClick={action.onClick}
                  className={cn(
                    'flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors',
                    action.variant === 'primary'
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  )}
                >
                  <action.icon className="w-3.5 h-3.5" />
                  {action.label}
                </button>
              ))}
            </div>
          </div>

          {/* Monthly Summary */}
          <div className="rounded-lg border bg-card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Monthly</h2>
            <div className="space-y-3">
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Spent</span>
                <span className="text-lg font-semibold tabular-nums">{formatCurrency(costSummary?.monthly || 0)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Limit</span>
                <span className="text-sm text-muted-foreground tabular-nums">{formatCurrency(costSummary?.monthly_limit || 1000)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Avg/Job</span>
                <span className="text-sm text-muted-foreground tabular-nums">{formatCurrency(costSummary?.avg_cost_per_job || 0)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Jobs</span>
                <span className="text-sm text-muted-foreground tabular-nums">{costSummary?.completed_jobs || 0} completed</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
