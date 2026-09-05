import { useState, useEffect } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, DollarSign } from 'lucide-react'
import { cn } from '@/lib/utils'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { wsClient, type WebSocketStatus } from '@/api/websocket'
import { formatCurrency } from '@/lib/utils'

export default function StatusBar() {
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>(wsClient.status)

  useEffect(() => {
    setWsStatus(wsClient.status)
    const cleanup = wsClient.on('ws_status', (data: { status: WebSocketStatus }) => {
      setWsStatus(data.status)
    })
    return cleanup
  }, [])

  const { data: jobStats, isSuccess: jobsOk } = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: () => jobsApi.getStats(),
    refetchInterval: 15000,
  })

  const { data: costSummary, isSuccess: costOk, isError: costError } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 60000,
  })

  // Online if WebSocket connected OR HTTP API responds
  const wsConnected = wsStatus === 'connected'
  const isOnline = wsConnected || jobsOk || costOk

  const activeJobs = (jobStats?.queued ?? 0) + (jobStats?.processing ?? 0)
  const moneyKnown = costOk && !costError && costSummary !== undefined
  const overBudget = moneyKnown && costSummary.over_budget
  const paidApiFrozen = moneyKnown && costSummary.paid_api_frozen
  const spendWallet = moneyKnown && costSummary.authority_mode === 'spend_wallet'
  const paidApiBlocked = true
  const unresolvedHolds = moneyKnown ? costSummary.unresolved_holds : 0
  const monthlyCap = moneyKnown ? costSummary.effective_monthly_limit : 0
  const monthlyExposure = moneyKnown ? costSummary.exposure.monthly : 0
  const walletExposure = spendWallet
    ? costSummary.spend_wallet_spent + costSummary.spend_wallet_reserved
    : 0
  const walletCap = spendWallet ? costSummary.spend_wallet_authorized : 0
  const monthlyUtilization =
    moneyKnown && monthlyCap > 0 ? (monthlyExposure / monthlyCap) * 100 : null
  const walletUtilization =
    spendWallet && walletCap > 0 ? (walletExposure / walletCap) * 100 : null
  const authorityUtilization = Math.max(monthlyUtilization ?? 0, walletUtilization ?? 0)
  const thresholdLabel =
    !moneyKnown
      ? null
      : authorityUtilization >= 100
        ? '100%'
        : authorityUtilization >= 95
          ? '95%'
          : authorityUtilization >= 80
            ? '80%'
            : authorityUtilization >= 50
              ? '50%'
              : null
  const connectionLabel = wsConnected
    ? 'Live updates connected'
    : isOnline && wsStatus === 'reconnecting'
      ? 'API online, live updates reconnecting'
      : isOnline
        ? 'API online, live updates unavailable'
        : 'Offline'
  const compactConnectionLabel = wsConnected
    ? 'Live'
    : isOnline && wsStatus === 'reconnecting'
      ? 'Reconnecting'
      : isOnline
        ? 'API only'
        : 'Offline'
  const exposureLabel = moneyKnown && spendWallet
    ? `${formatCurrency(walletExposure)} / ${formatCurrency(walletCap)} | Month ${formatCurrency(monthlyExposure)} / ${formatCurrency(monthlyCap)}`
    : moneyKnown
      ? `${formatCurrency(monthlyExposure)} / ${formatCurrency(monthlyCap)}`
      : 'UNKNOWN / UNKNOWN'
  const accountingLabel = `${spendWallet ? 'API wallet' : 'Month exposure'}: ${exposureLabel}`
  const blockingReason = !moneyKnown
    ? 'Accounting is unknown; paid API dispatch remains blocked.'
    : paidApiFrozen
      ? costSummary.freeze_reason || 'Paid API dispatch is frozen.'
      : 'Paid API dispatch is unavailable in this release, including when a local budget is funded.'

  return (
    <footer aria-label="Workspace status" className="flex min-h-8 shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t bg-background px-2 py-1 text-[11px] text-muted-foreground sm:px-4">
      {/* Left section */}
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <div className="hidden items-center gap-1.5 whitespace-nowrap lg:flex">
          <Activity className="h-3 w-3" />
          <span>
            {jobsOk ? `${activeJobs} active job${activeJobs !== 1 ? 's' : ''}` : 'Activity unknown'}
          </span>
        </div>

        <div className="hidden items-center gap-1.5 xl:flex">
          <DollarSign className="h-3 w-3" />
          <span>Today: {moneyKnown ? formatCurrency(costSummary.exposure.daily) : 'UNKNOWN'}</span>
          {thresholdLabel && !paidApiFrozen && (
            <span
              className={cn(
                'rounded px-1 font-medium',
                authorityUtilization >= 95
                  ? 'text-destructive'
                  : 'text-warning'
              )}
              title={`Paid authority reached the ${thresholdLabel} threshold of an effective ceiling`}
            >
              {thresholdLabel} authority
            </span>
          )}
        </div>

        <Link
          to="/costs"
          aria-label={`Open cost accounting. ${accountingLabel}. ${blockingReason}${unresolvedHolds > 0 ? ` ${unresolvedHolds} unresolved holds.` : ''}${overBudget ? ' Over budget.' : ''}`}
          className={cn(
            'flex min-h-6 min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 rounded underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring',
            overBudget && 'font-semibold text-destructive',
            (paidApiBlocked || unresolvedHolds > 0) && !overBudget && 'font-semibold text-warning'
          )}
          title={blockingReason}
        >
          <AlertTriangle aria-hidden="true" className="h-3 w-3 shrink-0" />
          <span>PAID API BLOCKED</span>
          <span className="xl:hidden">{!moneyKnown ? 'Costs unknown' : overBudget ? 'Over budget' : unresolvedHolds > 0 ? `${unresolvedHolds} holds` : 'Costs'}</span>
          <span className="hidden xl:inline">{accountingLabel}{unresolvedHolds > 0 && ` ${unresolvedHolds} UNRESOLVED HOLD${unresolvedHolds === 1 ? '' : 'S'}`}{overBudget && ' OVER BUDGET'}</span>
        </Link>
      </div>

      {/* Right section */}
      <div role="status" aria-label={connectionLabel} className="ml-auto flex shrink-0 items-center gap-1.5" title={connectionLabel}>
        <span
          aria-hidden="true"
          className={cn(
            'inline-block h-2 w-2 rounded-full',
            !isOnline
              ? 'bg-destructive'
              : wsConnected
                ? 'bg-green-500'
                : wsStatus === 'reconnecting'
                  ? 'bg-warning'
                  : 'bg-destructive'
          )}
        />
        <span className="xl:hidden">{compactConnectionLabel}</span>
        <span className="hidden xl:inline">{connectionLabel}</span>
      </div>
    </footer>
  )
}
