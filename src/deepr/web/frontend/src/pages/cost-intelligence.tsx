import { useState, useRef, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { costApi } from '@/api/cost'
import { cn, formatCurrency } from '@/lib/utils'
import { AreaChartComponent } from '@/components/charts/area-chart'
import { DonutChart } from '@/components/charts/donut-chart'
import { CHART_COLORS } from '@/lib/chart-theme'
import { toast } from 'sonner'
import {
  AlertTriangle,
  TrendingUp,
} from 'lucide-react'
import { FormSkeleton } from '@/components/ui/skeleton'

type TimeRange = '7d' | '30d' | '90d'

export default function CostIntelligence() {
  const queryClient = useQueryClient()
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')
  const days = timeRange === '7d' ? 7 : timeRange === '90d' ? 90 : 30

  const { data: summary, isLoading: isSummaryLoading, isError: isSummaryError, refetch: refetchSummary } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 30000,
  })

  const { data: trends } = useQuery({
    queryKey: ['cost', 'trends', days],
    queryFn: () => costApi.getTrends(days),
  })

  const {
    data: breakdown,
    isLoading: isBreakdownLoading,
    isError: isBreakdownError,
    isFetching: isBreakdownFetching,
    refetch: refetchBreakdown,
  } = useQuery({
    queryKey: ['cost', 'breakdown', timeRange],
    queryFn: () => costApi.getBreakdown(timeRange),
  })

  const { data: limits, isError: isLimitsError } = useQuery({
    queryKey: ['cost', 'limits'],
    queryFn: () => costApi.getLimits(),
  })

  // Local state keeps the canonical monthly slider stable during debounce.
  const [localMonthlyLimit, setLocalMonthlyLimit] = useState<number | null>(null)
  const moneyKnown = !isSummaryError && summary !== undefined
  const limitsKnown = !isLimitsError && limits !== undefined
  const effectiveMonthlyLimit = localMonthlyLimit ?? (limitsKnown ? limits.monthly : null)
  const moneyLabel = (value: number | undefined) =>
    moneyKnown && value !== undefined ? formatCurrency(value) : 'UNKNOWN'
  const limitLabel = (value: number | undefined) =>
    limitsKnown && value !== undefined ? formatCurrency(value) : 'UNKNOWN'

  const updateLimitsMutation = useMutation({
    mutationFn: costApi.updateLimits,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cost'] })
      setLocalMonthlyLimit(null)
    },
    onError: () => {
      toast.error('Failed to update budget limits')
      setLocalMonthlyLimit(null)
    },
  })

  // Debounce slider changes to avoid excessive API calls
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])
  const localMonthlyLimitRef = useRef(localMonthlyLimit)
  localMonthlyLimitRef.current = localMonthlyLimit

  const handleMonthlySliderChange = useCallback((value: number) => {
    setLocalMonthlyLimit(value)
    localMonthlyLimitRef.current = value
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (localMonthlyLimitRef.current !== null) {
        updateLimitsMutation.mutate({ monthly: localMonthlyLimitRef.current })
      }
    }, 500)
  }, [updateLimitsMutation])

  const dailyUtilization = !moneyKnown
    ? null
    : summary.effective_caps.daily > 0
      ? (summary.exposure.daily / summary.effective_caps.daily) * 100
      : summary.exposure.daily > 0 ? Number.POSITIVE_INFINITY : 0
  const monthlyUtilization = !moneyKnown
    ? null
    : summary.effective_caps.monthly > 0
      ? (summary.exposure.monthly / summary.effective_caps.monthly) * 100
      : summary.exposure.monthly > 0 ? Number.POSITIVE_INFINITY : 0
  const utilizationLabel = (value: number | null) =>
    value === null ? 'UNKNOWN' : Number.isFinite(value) ? `${value.toFixed(0)}%` : 'OVER $0 CEILING'

  const trendData = trends?.daily?.map((t: { date: string; cost: number }) => ({
    date: t.date,
    cost: t.cost,
  })) || []

  const breakdownData = Array.isArray(breakdown)
    ? breakdown.map((b: { model: string; cost: number }, i: number) => ({
        name: b.model,
        value: b.cost,
        color: CHART_COLORS[i % CHART_COLORS.length],
      }))
    : []

  const timeRanges: { key: TimeRange; label: string }[] = [
    { key: '7d', label: '7 Days' },
    { key: '30d', label: '30 Days' },
    { key: '90d', label: '90 Days' },
  ]

  if (isSummaryLoading) return <FormSkeleton />

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Cost Intelligence</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Spending analytics and budget management</p>
        </div>
        <div className="flex gap-1 p-1 bg-secondary rounded-lg">
          {timeRanges.map((tr) => (
            <button
              key={tr.key}
              onClick={() => setTimeRange(tr.key)}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs font-medium transition-all',
                timeRange === tr.key ? 'bg-background shadow-xs text-foreground' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tr.label}
            </button>
          ))}
        </div>
      </div>

      {/* Accuracy Disclaimer */}
      <div className="rounded-lg border bg-muted/30 px-4 py-2.5 flex items-start gap-2.5 text-xs text-muted-foreground">
        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        <p>
          Spend totals come from Deepr's append-only cost ledger and may not reflect exact provider billing.
          Imported or demo result costs do not create ledger spend. Check provider billing consoles for authoritative charges.
        </p>
      </div>

      {/* Error Banner */}
      {isSummaryError && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-destructive shrink-0" />
          <p className="text-sm text-foreground flex-1">
            Canonical money state is UNKNOWN. Paid API dispatch must remain blocked until accounting is readable.
          </p>
          <button
            onClick={() => refetchSummary()}
            className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:bg-primary/90 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* A zero ceiling is an explicit paid freeze, never a missing default. */}
      {summary?.paid_api_frozen && (
        <div className="rounded-lg border border-warning/40 bg-warning/5 p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-foreground">Paid API dispatch is frozen</p>
            <p className="text-sm text-muted-foreground mt-0.5">
              {summary.freeze_reason || 'The effective monthly paid API ceiling is $0.'} Local and proven plan-quota capacity remain available.
            </p>
          </div>
        </div>
      )}
      {moneyKnown && summary.unresolved_holds > 0 && (
        <div className="rounded-lg border border-warning/40 bg-warning/5 p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-foreground">Unresolved provider exposure</p>
            <p className="text-sm text-muted-foreground mt-0.5">
              {summary.unresolved_holds} post-dispatch hold{summary.unresolved_holds === 1 ? '' : 's'} totaling{' '}
              {formatCurrency(summary.unresolved_exposure)} require settlement reconciliation.
            </p>
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Monthly */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Monthly Exposure</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{moneyLabel(summary?.exposure.monthly)}</p>
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{moneyLabel(summary?.effective_caps.monthly)} limit</span>
              <span>{utilizationLabel(monthlyUtilization)}</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', monthlyUtilization === null || monthlyUtilization > 90 ? 'bg-destructive' : monthlyUtilization > 70 ? 'bg-warning' : 'bg-success')}
                style={{ width: `${monthlyUtilization === null ? 100 : Math.min(monthlyUtilization, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Today */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Today Exposure</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{moneyLabel(summary?.exposure.daily)}</p>
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{moneyLabel(summary?.effective_caps.daily)} limit</span>
              <span>{utilizationLabel(dailyUtilization)}</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', dailyUtilization === null || dailyUtilization > 90 ? 'bg-destructive' : dailyUtilization > 70 ? 'bg-warning' : 'bg-success')}
                style={{ width: `${dailyUtilization === null ? 100 : Math.min(dailyUtilization, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Active Holds */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Active Holds</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{moneyLabel(summary?.active_holds)}</p>
          <p className="text-xs text-muted-foreground">Accepted work awaiting settlement</p>
        </div>

        {/* Ledger Total */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Ledger Total</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{moneyLabel(summary?.settled.total)}</p>
          <p className="text-xs text-muted-foreground">All settled Deepr operations</p>
        </div>
      </div>

      {/* Budget Alert */}
      {moneyKnown && !summary.paid_api_frozen && (
        (dailyUtilization !== null && dailyUtilization > 80) ||
        (monthlyUtilization !== null && monthlyUtilization > 80)
      ) && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-foreground">Budget Alert</p>
            <div className="text-sm text-muted-foreground mt-0.5">
              {dailyUtilization !== null && dailyUtilization > 80 && <p>Daily exposure at {dailyUtilization.toFixed(0)}% of limit</p>}
              {monthlyUtilization !== null && monthlyUtilization > 80 && <p>Monthly exposure at {monthlyUtilization.toFixed(0)}% of limit</p>}
            </div>
          </div>
        </div>
      )}

      {/* Spending Trend */}
      <div className="rounded-lg border bg-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Spending Trend</h2>
          <TrendingUp className="w-4 h-4 text-muted-foreground" />
        </div>
        {trendData.length > 0 ? (
          <AreaChartComponent
            data={trendData}
            dataKey="cost"
            xAxisKey="date"
            height={250}
            formatTooltip={(v) => formatCurrency(v)}
            formatXAxis={(d) => {
              const date = new Date(d)
              return `${date.getMonth() + 1}/${date.getDate()}`
            }}
          />
        ) : (
          <div className="h-[250px] flex items-center justify-center text-sm text-muted-foreground">
            No trend data available
          </div>
        )}
      </div>

      {/* Budget Controls - prominent section */}
      <div className="rounded-lg border-2 border-primary/20 bg-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Budget Controls</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Review effective caps and narrow monthly authority</p>
          </div>
          {updateLimitsMutation.isPending && (
            <span className="text-xs text-muted-foreground animate-pulse">Saving...</span>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="rounded-lg border bg-muted/20 p-3 space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Effective per-job limit</p>
            <p className="text-lg font-semibold text-foreground tabular-nums">{limitLabel(limits?.per_job)}</p>
            <p className="text-[10px] text-muted-foreground">Environment-managed global cap</p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-3 space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Effective daily limit</p>
            <p className="text-lg font-semibold text-foreground tabular-nums">{limitLabel(limits?.daily)}</p>
            <p className="text-[10px] text-muted-foreground">Environment-managed global cap</p>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-baseline">
              <span className="text-xs font-medium text-muted-foreground">Canonical monthly limit</span>
              <span className="text-lg font-semibold text-foreground tabular-nums">
                {effectiveMonthlyLimit === null ? 'UNKNOWN' : formatCurrency(effectiveMonthlyLimit)}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(limits?.monthly ?? 0, 1)}
              step={0.01}
              value={effectiveMonthlyLimit ?? 0}
              onChange={(e) => handleMonthlySliderChange(parseFloat(e.target.value))}
              aria-label={`Canonical monthly limit, currently ${effectiveMonthlyLimit === null ? 'UNKNOWN' : formatCurrency(effectiveMonthlyLimit)}`}
              aria-valuemin={0}
              aria-valuemax={Math.max(limits?.monthly ?? 0, 1)}
              aria-valuenow={effectiveMonthlyLimit ?? undefined}
              disabled={!moneyKnown || !limitsKnown || limits.monthly <= 0}
              className="w-full h-2 bg-secondary rounded-full appearance-none cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground/60">
              <span>$0 freezes paid APIs</span>
              <span>{limitsKnown ? formatCurrency(Math.max(limits.monthly, 1)) : 'UNKNOWN'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Cost Breakdown Pie Chart */}
      <div className="rounded-lg border bg-card p-5 space-y-4">
        <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Spending by Model</h2>
        {isBreakdownLoading ? (
          <div className="h-[220px] flex items-center justify-center text-sm text-muted-foreground">
            Loading model spending...
          </div>
        ) : isBreakdownError ? (
          <div className="h-[220px] flex flex-col gap-3 items-center justify-center text-sm text-muted-foreground">
            <span>Unable to load model spending from the cost ledger.</span>
            <button
              type="button"
              onClick={() => void refetchBreakdown()}
              disabled={isBreakdownFetching}
              className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {isBreakdownFetching ? 'Retrying...' : 'Retry'}
            </button>
          </div>
        ) : breakdownData.length > 0 ? (
          <div className="flex flex-col sm:flex-row items-center gap-6">
            <DonutChart data={breakdownData} height={220} innerRadius={60} outerRadius={90} />
            <div className="space-y-2 flex-1 min-w-0">
              {breakdownData.map((item: { name: string; value: number; color: string }) => (
                <div key={item.name} className="flex items-center gap-2 text-sm">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: item.color }} />
                  <span className="flex-1 text-foreground text-xs truncate">{item.name}</span>
                  <span className="text-muted-foreground text-xs tabular-nums">{formatCurrency(item.value)}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="h-[220px] flex items-center justify-center text-sm text-muted-foreground">
            No model-attributed ledger events in this time range
          </div>
        )}
      </div>
    </div>
  )
}
