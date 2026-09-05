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
  Search,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { Sparkline } from '@/components/charts/sparkline'
import { Button } from '@/components/ui/button'
import PartialQueryError from '@/components/shared/partial-query-error'

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

  const { data: jobsData, isLoading: isJobsLoading, isError: isJobsError, refetch: refetchJobs, isFetching: isJobsFetching } = useQuery({
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
  const authorityExposure = moneyKnown && costSummary.authority_mode === 'spend_wallet'
    ? costSummary.spend_wallet_spent + costSummary.spend_wallet_reserved
    : costSummary?.exposure.monthly
  const authorityLimit = moneyKnown && costSummary.authority_mode === 'spend_wallet'
    ? costSummary.spend_wallet_authorized
    : costSummary?.effective_caps.monthly

  const trendData = trends?.daily?.map((t: { cost: number }) => ({ value: t.cost })) || []

  const quickActions = [
    { label: 'Explore Experts', icon: Users, onClick: () => navigate('/experts'), variant: 'primary' as const },
    { label: 'View Results', icon: Search, onClick: () => navigate('/results'), variant: 'secondary' as const },
    { label: 'Research Preview', icon: Search, onClick: () => navigate('/research'), variant: 'secondary' as const },
    { label: 'Check Costs', icon: DollarSign, onClick: () => navigate('/costs'), variant: 'secondary' as const },
  ]

  return (
    <div className="space-y-6 p-4 sm:p-6 animate-fade-in">
      {/* Greeting + CTA */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Overview</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Your local expert workspace</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild><Link to="/experts"><Users className="w-4 h-4" />Explore Experts</Link></Button>
          <Button asChild variant="outline"><Link to="/research">Research Preview</Link></Button>
        </div>
      </div>

      {/* Connection warning */}
      {isJobsError && (
        <PartialQueryError title="Activity is unavailable" description="The server could not return job state. This does not mean the workspace is empty." onRetry={() => void refetchJobs()} retrying={isJobsFetching} />
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
      {moneyKnown && costSummary.authority_mode === 'spend_wallet' && (
        <div className="rounded-lg border border-success/40 bg-success/5 px-4 py-3 flex items-center gap-3">
          <DollarSign className="w-4 h-4 text-success shrink-0" />
          <p className="text-sm text-foreground">
            <span className="font-semibold text-success">Metered API wallet:</span>{' '}
            {formatCurrency(costSummary.spend_wallet_available)} of{' '}
            {formatCurrency(costSummary.spend_wallet_authorized)} is available after settled spend and active holds.
            This is a local Deepr ceiling, not provider prepaid credit. A verified provider hard boundary is also required.
            Local and verified plan-quota work is $0 at the margin and does not draw it down.
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
            {formatCurrency(costSummary.exposure.monthly)} exposed under the current authority, including active holds, against a{' '}
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

      {/*
        One line of live state, not four cards.

        The quad it replaces - active / completed / failed / today's spend -
        is the most recognizable shape in generated dashboards, and here it
        was also mostly untrue: three of the four numbers never move on a
        local-first install where paid dispatch is frozen, and the fourth
        counted 323 queued jobs that cannot run. A row of large numerals that
        do not change is decoration.
      */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border bg-card px-4 py-3 text-sm">
        <span className="flex items-center gap-2">
          <span
            className={cn(
              'status-dot',
              processingCount > 0 ? 'text-info animate-pulse' : queuedCount > 0 ? 'text-warning' : 'text-muted-foreground'
            )}
          />
          <span className="data-figure font-medium text-foreground">{activeCount}</span>
          <span className="text-muted-foreground">active</span>
        </span>
        <span className="text-muted-foreground">
          <span className="data-figure text-foreground">{completedCount}</span> completed
        </span>
        {failedCount > 0 && (
          <span className="text-muted-foreground">
            <span className="data-figure text-destructive">{failedCount}</span> failed
          </span>
        )}
        <span className="text-muted-foreground">
          <span className="data-figure text-foreground">{moneyLabel(costSummary?.exposure.daily)}</span> today of{' '}
          <span className="data-figure">{moneyLabel(costSummary?.effective_caps.daily)}</span>
        </span>
        {/* Kept visible rather than folded into a percentage bar: OVER $0
            CEILING and UNKNOWN are the two readings that matter here, and a
            progress bar renders both as "some width". */}
        {dailyUtilizationLabel !== '0%' && (
          <span
            className={cn(
              'text-2xs uppercase',
              dailyUtilization === null || !Number.isFinite(dailyUtilization ?? 0)
                ? 'text-destructive'
                : 'text-muted-foreground'
            )}
          >
            {dailyUtilizationLabel}
          </span>
        )}
        <span className="ml-auto text-2xs uppercase text-muted-foreground">
          local and prepaid quota only
        </span>
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
              {isJobsLoading ? (
                <p role="status" className="p-8 text-sm text-muted-foreground">Loading recent activity...</p>
              ) : isJobsError && jobs.length === 0 ? (
                <p className="p-8 text-sm text-muted-foreground">Recent activity could not be loaded. Retry above to inspect it.</p>
              ) : jobs.length === 0 ? (
                <div className="p-8 space-y-4">
                  <p className="text-sm font-medium text-foreground text-center mb-4">Start with a local expert</p>
                  <div className="space-y-3 max-w-sm mx-auto">
                    <div className="flex items-start gap-3">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">1</span>
                      <div>
                        <p className="text-sm text-foreground">Create or choose an expert</p>
                        <p className="text-xs text-muted-foreground">
                          Open <Link to="/experts" className="text-primary underline underline-offset-2">Experts</Link> to define a domain or inspect an existing expert.
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">2</span>
                      <div>
                        <p className="text-sm text-foreground">Retain and study trusted evidence</p>
                        <p className="text-xs text-muted-foreground">
                          Use the local CLI to retain sources, study them, and form a brief. <Link to="/help" className="text-primary underline underline-offset-2">Open local setup guidance</Link>.
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center mt-0.5">3</span>
                      <div>
                        <p className="text-sm text-foreground">Inspect evidence and consult locally</p>
                        <p className="text-xs text-muted-foreground">
                          Review the expert's claims and uncertainty here. Its profile provides the CLI handoff for a local consultation.
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
                      ? 'bg-primary text-primary-foreground hover:bg-primary-hover'
                      : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                  )}
                >
                  <action.icon className="w-3.5 h-3.5" />
                  {action.label}
                </button>
              ))}
            </div>
          </div>

          {/* Governing paid-spend authority */}
          <div className="rounded-lg border bg-card p-5 space-y-3">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">
              {costSummary?.authority_mode === 'spend_wallet' ? 'API Wallet' : 'Monthly'}
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Exposure</span>
                <span className="text-lg font-semibold tabular-nums">{moneyLabel(authorityExposure)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-sm text-muted-foreground">Limit</span>
                <span className="text-sm text-muted-foreground tabular-nums">{moneyLabel(authorityLimit)}</span>
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
