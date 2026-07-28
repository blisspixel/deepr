import { Link, useNavigate } from 'react-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { formatCurrency, formatRelativeTime } from '@/lib/utils'
import { cn } from '@/lib/utils'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  DollarSign,
  Loader2,
  Plus,
  Search,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { Sparkline } from '@/components/charts/sparkline'

export default function Overview() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const cleanupMutation = useMutation({
    mutationFn: () => jobsApi.cleanupStale(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      toast.success(
        data.cleaned === 1
          ? 'Marked 1 stale job as failed'
          : `Marked ${data.cleaned} stale jobs as failed`
      )
    },
    onError: (error: Error) => {
      toast.error('Stale-job cleanup failed', {
        description: error.message || 'The server could not complete cleanup safely.',
      })
    },
  })

  const { data: jobsData, isError: isJobsError } = useQuery({
    queryKey: ['jobs', 'recent'],
    queryFn: () => jobsApi.list({ limit: 10 }),
    refetchInterval: 5000,
  })

  const { data: jobStats } = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: () => jobsApi.getStats(),
    refetchInterval: 10000,
  })

  const { data: costSummary, isError: isCostError } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 10000,
  })

  const { data: trends } = useQuery({
    queryKey: ['cost', 'trends', 14],
    queryFn: () => costApi.getTrends(14),
  })

  const { data: integrity, isError: isIntegrityError } = useQuery({
    queryKey: ['cost', 'integrity'],
    queryFn: () => costApi.getIntegrity(),
    refetchInterval: 60000,
  })

  const jobs = jobsData?.jobs || []
  const liveJobs = jobs.filter(j => ['queued', 'processing'].includes(j.status))
  const completedCount = jobStats?.completed ?? jobs.filter(j => j.status === 'completed').length
  const failedCount = jobStats?.failed ?? jobs.filter(j => j.status === 'failed').length
  const queuedCount = jobStats?.queued ?? liveJobs.filter(j => j.status === 'queued').length
  const processingCount = jobStats?.processing ?? liveJobs.filter(j => j.status === 'processing').length
  const activeCount = queuedCount + processingCount
  const moneyKnown = !isCostError && costSummary !== undefined
  const moneyLabel = (value: number | undefined) =>
    moneyKnown && value !== undefined ? formatCurrency(value) : 'UNKNOWN'
  const dailyUtilization = !moneyKnown
    ? null
    : costSummary.effective_caps.daily > 0
      ? (costSummary.exposure.daily / costSummary.effective_caps.daily) * 100
      : costSummary.exposure.daily > 0 ? Number.POSITIVE_INFINITY : 0
  const dailyUtilizationLabel = dailyUtilization === null
    ? 'UNKNOWN'
    : Number.isFinite(dailyUtilization) ? `${dailyUtilization.toFixed(0)}%` : 'OVER $0 CEILING'

  const trendData = trends?.daily?.map((t: { cost: number }) => ({ value: t.cost })) || []

  const quickActions = [
    { label: 'New Research', icon: Plus, onClick: () => navigate('/research'), variant: 'primary' as const },
    { label: 'View Results', icon: Search, onClick: () => navigate('/results'), variant: 'secondary' as const },
    { label: 'Ask Expert', icon: Users, onClick: () => navigate('/experts'), variant: 'secondary' as const },
    { label: 'Check Costs', icon: DollarSign, onClick: () => navigate('/costs'), variant: 'secondary' as const },
  ]

  return (
    <div className="space-y-6 p-4 sm:p-6 animate-fade-in">
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

      {/* Connection warning */}
      {isJobsError && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0" />
          <p className="text-sm text-muted-foreground">
            Unable to load job state. Operational data below may be incomplete.
            Start the server or go to{' '}
            <button onClick={() => navigate('/settings')} className="text-primary hover:underline">Settings</button>
            {' '}to load demo data.
          </p>
        </div>
      )}

      {/* Spend truth: over-budget and orphaned spend must be impossible to
          miss. A 30-job campaign once billed $37.79 with zero surviving
          artifacts and the dashboard showed nothing. */}
      {costSummary?.paid_api_frozen && (
        <div className="rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0" />
          <p className="text-sm text-foreground">
            <span className="font-semibold text-warning">Paid API frozen:</span>{' '}
            {costSummary.freeze_reason || 'the effective monthly paid API ceiling is $0.'} Local and proven
            plan-quota capacity remain available.
          </p>
        </div>
      )}
      {moneyKnown && costSummary.unresolved_holds > 0 && (
        <div className="rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0" />
          <p className="text-sm text-foreground">
            <span className="font-semibold text-warning">Unresolved provider exposure:</span>{' '}
            {costSummary.unresolved_holds} post-dispatch hold{costSummary.unresolved_holds === 1 ? '' : 's'} totaling{' '}
            {formatCurrency(costSummary.unresolved_exposure)} require settlement reconciliation.
          </p>
        </div>
      )}
      {!moneyKnown && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-destructive shrink-0" />
          <p className="text-sm text-foreground">
            <span className="font-semibold text-destructive">Canonical money state UNKNOWN:</span>{' '}
            paid API dispatch must remain blocked until accounting is readable.
          </p>
        </div>
      )}
      {isIntegrityError && (
        <div className="rounded-lg border border-warning/40 bg-warning/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0" />
          <p className="text-sm text-foreground">
            Artifact reconciliation is UNKNOWN. No conclusion about orphaned spend is available.
          </p>
        </div>
      )}
      {costSummary?.over_budget && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-destructive shrink-0" />
          <p className="text-sm text-foreground">
            <span className="font-semibold text-destructive">Over budget:</span>{' '}
            {formatCurrency(costSummary.exposure.monthly)} exposed this month, including active holds, against a{' '}
            {formatCurrency(costSummary.effective_monthly_limit)} limit. Metered dispatch
            should be blocked; review{' '}
            <Link to="/costs" className="text-primary hover:underline">Costs</Link> before approving anything.
          </p>
        </div>
      )}
      {(integrity?.orphaned_spend ?? 0) > 0.005 && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-destructive shrink-0" />
          <p className="text-sm text-foreground">
            <span className="font-semibold text-destructive">Orphaned spend:</span>{' '}
            {formatCurrency(integrity!.orphaned_spend)} across {integrity!.orphaned_events} paid events
            in the last {integrity!.days} days has no surviving report artifact. Audit with{' '}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">deepr costs doctor</code>.
          </p>
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {/* Active Jobs */}
        <div className="rounded-lg border bg-card p-3 sm:p-5 space-y-2">
          <div className="flex items-center gap-2">
            {processingCount > 0 && <span className="w-2 h-2 rounded-full bg-info animate-pulse" />}
            {processingCount === 0 && queuedCount > 0 && <span className="w-2 h-2 rounded-full bg-warning" />}
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Active Jobs</p>
          </div>
          <p className="text-2xl sm:text-3xl font-semibold text-foreground tabular-nums">{activeCount}</p>
          <p className="text-xs text-muted-foreground">
            {activeCount > 0 ? `${queuedCount} queued, ${processingCount} processing` : 'No active jobs'}
          </p>
        </div>

        {/* Completed */}
        <div className="rounded-lg border bg-card p-3 sm:p-5 space-y-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Completed</p>
          </div>
          <p className="text-2xl sm:text-3xl font-semibold text-foreground tabular-nums">{completedCount}</p>
          <p className="text-xs text-muted-foreground">All time</p>
        </div>

        {/* Failed */}
        <div className="rounded-lg border bg-card p-3 sm:p-5 space-y-2">
          <div className="flex items-center gap-2">
            <XCircle className="w-3.5 h-3.5 text-destructive" />
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Failed</p>
          </div>
          <p className="text-2xl sm:text-3xl font-semibold text-foreground tabular-nums">{failedCount}</p>
          <p className="text-xs text-muted-foreground">All time</p>
        </div>

        {/* Daily Spend */}
        <div className="rounded-lg border bg-card p-3 sm:p-5 space-y-2">
          <div className="flex items-center gap-2">
            <DollarSign className="w-3.5 h-3.5 text-muted-foreground" />
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Today</p>
          </div>
          <p className="text-2xl sm:text-3xl font-semibold text-foreground tabular-nums">
            {moneyLabel(costSummary?.exposure.daily)}
          </p>
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{moneyLabel(costSummary?.effective_caps.daily)} limit</span>
              <span>{dailyUtilizationLabel}</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  dailyUtilization === null || dailyUtilization > 90 ? 'bg-destructive' :
                  dailyUtilization > 70 ? 'bg-warning' : 'bg-success'
                )}
                style={{ width: `${dailyUtilization === null ? 100 : Math.min(dailyUtilization, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Jobs + Activity */}
        <div className="lg:col-span-2 space-y-6">
          {/* Recent Active Jobs */}
          {liveJobs.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Recent Active Jobs</h2>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      if (window.confirm('Mark queued and processing jobs older than 30 minutes as failed? Processing jobs missing required provider state are also included. Recent healthy jobs are unaffected.')) {
                        cleanupMutation.mutate()
                      }
                    }}
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
                  <span className="text-xs text-muted-foreground">
                    Showing {liveJobs.length} of {activeCount} active
                  </span>
                </div>
              </div>
              <div className="space-y-2">
                {liveJobs.map((job) => (
                  <Link
                    key={job.id}
                    to={`/research/${job.id}`}
                    className="block rounded-lg border bg-card p-4 hover:border-primary/30 hover:shadow-md transition-all focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex justify-between items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {job.prompt.substring(0, 80)}{job.prompt.length > 80 ? '...' : ''}
                        </p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-xs text-muted-foreground">{job.model}</span>
                          <span className="text-border">·</span>
                          <span className={cn(
                            'inline-flex items-center gap-1 text-xs',
                            job.status === 'processing' ? 'text-info' : 'text-warning'
                          )}>
                            {job.status === 'processing'
                              ? <Loader2 className="w-3 h-3 animate-spin" />
                              : <Clock3 className="w-3 h-3" />}
                            {job.status === 'processing' ? 'Analyzing' : 'Queued'}
                          </span>
                          <span className="text-border">·</span>
                          <span className="text-xs text-muted-foreground">
                            Submitted {formatRelativeTime(job.submitted_at)}
                          </span>
                        </div>
                      </div>
                      {job.cost > 0 && (
                        <span className="text-sm font-medium text-muted-foreground tabular-nums">
                          ~{formatCurrency(job.cost)}
                        </span>
                      )}
                    </div>
                    {job.status === 'processing' && (
                      <div className="mt-3 w-full h-1 bg-secondary rounded-full overflow-hidden" aria-hidden="true">
                        <div className="h-full bg-primary/60 rounded-full animate-pulse w-full" />
                      </div>
                    )}
                  </Link>
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
                      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">1</span>
                      <div>
                        <p className="text-sm text-foreground">Set a budget</p>
                        <p className="text-xs text-muted-foreground">
                          Configure spending limits in{' '}
                          <button onClick={() => navigate('/costs')} className="text-primary hover:underline">
                            Cost Intelligence
                          </button>
                          {' '}to cap daily and monthly spending
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">2</span>
                      <div>
                        <p className="text-sm text-foreground">Run a research job</p>
                        <p className="text-xs text-muted-foreground">
                          Use the <button onClick={() => navigate('/research')} className="text-primary hover:underline">Research Studio</button> or CLI to submit a query
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">3</span>
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
                  <Link
                    key={job.id}
                    to={['queued', 'processing'].includes(job.status) ? `/research/${job.id}` : `/results/${job.id}`}
                    className="px-4 py-3 flex items-center gap-3 hover:bg-accent/50 transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                  >
                    <div className="shrink-0">
                      {job.status === 'completed' ? <CheckCircle2 className="w-4 h-4 text-success" /> :
                       job.status === 'processing' ? <Loader2 className="w-4 h-4 text-info animate-spin" /> :
                       job.status === 'queued' ? <Activity className="w-4 h-4 text-warning" /> :
                       job.status === 'failed' ? <XCircle className="w-4 h-4 text-destructive" /> :
                       job.status === 'cancelled' ? <XCircle className="w-4 h-4 text-muted-foreground" /> :
                       <Activity className="w-4 h-4 text-muted-foreground" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground truncate">
                        {job.prompt
                          ? `${job.prompt.substring(0, 60)}${job.prompt.length > 60 ? '...' : ''}`
                          : <span className="italic text-muted-foreground">Untitled research</span>
                        }
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {job.model && (
                        <span className="text-[10px] text-muted-foreground px-1.5 py-0.5 rounded bg-muted">
                          {job.model.split('/').pop()}
                        </span>
                      )}
                      {job.cost > 0 && (
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {formatCurrency(job.cost)}
                        </span>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {job.submitted_at ? formatRelativeTime(job.submitted_at) : ''}
                      </span>
                    </div>
                  </Link>
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
                <span className="text-sm text-muted-foreground">Exposure</span>
                <span className="text-lg font-semibold tabular-nums">{moneyLabel(costSummary?.exposure.monthly)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Limit</span>
                <span className="text-sm text-muted-foreground tabular-nums">{moneyLabel(costSummary?.effective_caps.monthly)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Active holds</span>
                <span className="text-sm text-muted-foreground tabular-nums">{moneyLabel(costSummary?.active_holds)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Ledger total</span>
                <span className="text-sm text-muted-foreground tabular-nums">{moneyLabel(costSummary?.settled.total)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Queue progress</span>
                <span className="text-sm text-muted-foreground tabular-nums">
                  {costSummary?.completed_jobs ?? 0} of {costSummary?.total_jobs ?? 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
