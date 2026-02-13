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

type TimeRange = '7d' | '30d' | '90d'

export default function CostIntelligence() {
  const queryClient = useQueryClient()
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')
  const days = timeRange === '7d' ? 7 : timeRange === '90d' ? 90 : 30

  const { data: summary, isError: isSummaryError, refetch: refetchSummary } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 30000,
  })

  const { data: trends } = useQuery({
    queryKey: ['cost', 'trends', days],
    queryFn: () => costApi.getTrends(days),
  })

  const { data: breakdown } = useQuery({
    queryKey: ['cost', 'breakdown', timeRange],
    queryFn: () => costApi.getBreakdown(timeRange),
  })

  const { data: limits } = useQuery({
    queryKey: ['cost', 'limits'],
    queryFn: () => costApi.getLimits(),
  })

  // Local state for sliders so they don't snap back during debounce
  const [localLimits, setLocalLimits] = useState<{ per_job: number; daily: number; monthly: number } | null>(null)
  const effectiveLimits = localLimits ?? limits

  // Sync from server when query data arrives (only if user hasn't overridden locally)
  useEffect(() => {
    if (limits && !localLimits) {
      setLocalLimits({ per_job: limits.per_job, daily: limits.daily, monthly: limits.monthly })
    }
  }, [limits, localLimits])

  const updateLimitsMutation = useMutation({
    mutationFn: costApi.updateLimits,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cost'] })
      // Allow server values to re-sync (e.g. if server clamped the values)
      setLocalLimits(null)
    },
    onError: () => {
      toast.error('Failed to update budget limits')
      // Reset local state to server values on error
      setLocalLimits(null)
    },
  })

  // Debounce slider changes to avoid excessive API calls
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])
  const localLimitsRef = useRef(localLimits)
  localLimitsRef.current = localLimits

  const handleSliderChange = useCallback((key: 'per_job' | 'daily' | 'monthly', value: number) => {
    setLocalLimits(prev => {
      const next = prev ? { ...prev, [key]: value } : { per_job: 20, daily: 100, monthly: 1000, [key]: value }
      localLimitsRef.current = next
      return next
    })
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (localLimitsRef.current) {
        updateLimitsMutation.mutate(localLimitsRef.current)
      }
    }, 500)
  }, [updateLimitsMutation])

  const dailyUtilization = summary && summary.daily_limit > 0
    ? (summary.daily / summary.daily_limit) * 100
    : 0
  const monthlyUtilization = summary && summary.monthly_limit > 0
    ? (summary.monthly / summary.monthly_limit) * 100
    : 0

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
                timeRange === tr.key ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tr.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error Banner */}
      {isSummaryError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-destructive flex-shrink-0" />
          <p className="text-sm text-foreground flex-1">Failed to load cost data.</p>
          <button
            onClick={() => refetchSummary()}
            className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:bg-primary/90 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Monthly */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Monthly</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{formatCurrency(summary?.monthly || 0)}</p>
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{formatCurrency(summary?.monthly_limit || 1000)} limit</span>
              <span>{monthlyUtilization.toFixed(0)}%</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', monthlyUtilization > 90 ? 'bg-destructive' : monthlyUtilization > 70 ? 'bg-warning' : 'bg-success')}
                style={{ width: `${Math.min(monthlyUtilization, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Today */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Today</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{formatCurrency(summary?.daily || 0)}</p>
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{formatCurrency(summary?.daily_limit || 100)} limit</span>
              <span>{dailyUtilization.toFixed(0)}%</span>
            </div>
            <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all', dailyUtilization > 90 ? 'bg-destructive' : dailyUtilization > 70 ? 'bg-warning' : 'bg-success')}
                style={{ width: `${Math.min(dailyUtilization, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Avg/Job */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Avg per Job</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">{formatCurrency(summary?.avg_cost_per_job || 0)}</p>
          <p className="text-xs text-muted-foreground">{summary?.completed_jobs || 0} completed</p>
        </div>

        {/* Success Rate */}
        <div className="rounded-lg border bg-card p-5 space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Success Rate</p>
          <p className="text-2xl font-semibold text-foreground tabular-nums">
            {summary?.total_jobs ? `${((summary.completed_jobs / summary.total_jobs) * 100).toFixed(0)}%` : 'N/A'}
          </p>
          <p className="text-xs text-muted-foreground">
            {summary?.completed_jobs || 0}/{summary?.total_jobs || 0} jobs
          </p>
        </div>
      </div>

      {/* Budget Alert */}
      {(dailyUtilization > 80 || monthlyUtilization > 80) && (
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-foreground">Budget Alert</p>
            <div className="text-sm text-muted-foreground mt-0.5">
              {dailyUtilization > 80 && <p>Daily spending at {dailyUtilization.toFixed(0)}% of limit</p>}
              {monthlyUtilization > 80 && <p>Monthly spending at {monthlyUtilization.toFixed(0)}% of limit</p>}
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

      {/* Breakdown + Budget Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* By Model */}
        <div className="rounded-lg border bg-card p-5 space-y-4">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">By Model</h2>
          {breakdownData.length > 0 ? (
            <div className="flex items-center gap-6">
              <DonutChart data={breakdownData} height={160} innerRadius={45} outerRadius={65} />
              <div className="space-y-2 flex-1">
                {breakdownData.map((item: { name: string; value: number; color: string }) => (
                  <div key={item.name} className="flex items-center gap-2 text-sm">
                    <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
                    <span className="flex-1 text-foreground text-xs">{item.name}</span>
                    <span className="text-muted-foreground text-xs tabular-nums">{formatCurrency(item.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-[160px] flex items-center justify-center text-sm text-muted-foreground">
              No breakdown data
            </div>
          )}
        </div>

        {/* Budget Controls */}
        <div className="rounded-lg border bg-card p-5 space-y-4">
          <h2 className="text-sm font-semibold text-foreground uppercase tracking-wider">Budget Controls</h2>
          <div className="space-y-4">
            {[
              { label: 'Per-job limit', key: 'per_job' as const, value: effectiveLimits?.per_job || 20, max: 50 },
              { label: 'Daily limit', key: 'daily' as const, value: effectiveLimits?.daily || 100, max: 500 },
              { label: 'Monthly limit', key: 'monthly' as const, value: effectiveLimits?.monthly || 1000, max: 5000 },
            ].map((control) => (
              <div key={control.key} className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{control.label}</span>
                  <span className="text-foreground font-medium tabular-nums">{formatCurrency(control.value)}</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={control.max}
                  step={control.max > 100 ? 10 : 1}
                  value={control.value}
                  onChange={(e) => handleSliderChange(control.key, parseFloat(e.target.value))}
                  className="w-full h-1.5 bg-secondary rounded-full appearance-none cursor-pointer accent-primary"
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
