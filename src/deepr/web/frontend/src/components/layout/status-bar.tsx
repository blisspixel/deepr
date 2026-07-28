import { useState, useEffect } from 'react'
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
  const paidApiBlocked = !moneyKnown || paidApiFrozen
  const unresolvedHolds = moneyKnown ? costSummary.unresolved_holds : 0
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

  return (
    <div className="flex h-8 items-center justify-between gap-2 border-t bg-background px-2 text-[11px] text-muted-foreground sm:px-4">
      {/* Left section */}
      <div className="flex min-w-0 items-center gap-2 sm:gap-4">
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          <Activity className="h-3 w-3" />
          <span>
            {activeJobs} active job{activeJobs !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="hidden items-center gap-1.5 sm:flex">
          <DollarSign className="h-3 w-3" />
          <span>Today: {moneyKnown ? formatCurrency(costSummary.exposure.daily) : 'UNKNOWN'}</span>
        </div>

        {/* Month spend vs the governing budget, always visible: the exact
            number the approval gate uses, red when over. A $37.99 month once
            showed nowhere until the bill arrived. */}
        <div
          className={cn(
            'flex items-center gap-1.5 whitespace-nowrap',
            overBudget && 'font-semibold text-destructive',
            (paidApiBlocked || unresolvedHolds > 0) && !overBudget && 'font-semibold text-warning'
          )}
          title={
            !moneyKnown
              ? 'Canonical money state is unavailable; paid API dispatch must remain blocked'
              : overBudget
              ? 'Monthly exposure exceeds the effective ceiling'
              : paidApiFrozen
                ? costSummary.freeze_reason || 'Paid API dispatch is frozen'
                : `Includes ${formatCurrency(costSummary.active_holds)} in active holds`
          }
        >
          {(overBudget || paidApiBlocked || unresolvedHolds > 0) && <AlertTriangle className="h-3 w-3" />}
          <span>
            Month exposure:{' '}
            {moneyKnown
              ? `${formatCurrency(costSummary.exposure.monthly)} / ${formatCurrency(costSummary.effective_monthly_limit)}`
              : 'UNKNOWN / UNKNOWN'}
            {!moneyKnown && ' PAID API BLOCKED'}
            {paidApiFrozen && ' PAID API FROZEN'}
            {unresolvedHolds > 0 && ` ${unresolvedHolds} UNRESOLVED HOLD${unresolvedHolds === 1 ? '' : 'S'}`}
            {overBudget && ' OVER BUDGET'}
          </span>
        </div>
      </div>

      {/* Right section */}
      <div role="status" aria-label={connectionLabel} className="flex min-w-0 items-center gap-1.5" title={connectionLabel}>
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
        <span className="sm:hidden">{compactConnectionLabel}</span>
        <span className="hidden sm:inline">{connectionLabel}</span>
      </div>
    </div>
  )
}
