import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { costApi } from '@/api/cost'
import Card, { CardBody } from '@/components/common/Card'
import Select from '@/components/common/Select'

type TimeRange = '7d' | '30d' | '90d'

export default function CostAnalytics() {
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')

  // Fetch cost summary
  const { data: summary } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 30000,
  })

  const dailyUtilization = summary
    ? (summary.daily / summary.daily_limit) * 100
    : 0
  const monthlyUtilization = summary
    ? (summary.monthly / summary.monthly_limit) * 100
    : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Analytics
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            Track spending and usage
          </p>
        </div>
        <Select
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value as TimeRange)}
          options={[
            { value: '7d', label: 'Last 7 Days' },
            { value: '30d', label: 'Last 30 Days' },
            { value: '90d', label: 'Last 90 Days' },
          ]}
        />
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Daily Spending */}
        <Card>
          <CardBody>
            <div className="space-y-2">
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                Today
              </p>
              <p className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                ${summary?.daily.toFixed(2) || '0.00'}
              </p>
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-[var(--color-text-secondary)]">
                    ${summary?.daily_limit.toFixed(2) || '100.00'} limit
                  </span>
                  <span className="text-[var(--color-text-secondary)] font-medium">
                    {dailyUtilization.toFixed(0)}%
                  </span>
                </div>
                <div className="progress-track">
                  <div
                    className={clsx(
                      'progress-fill',
                      dailyUtilization > 90 ? 'progress-error' :
                      dailyUtilization > 70 ? 'progress-warning' : 'progress-success'
                    )}
                    style={{ width: `${Math.min(dailyUtilization, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Monthly Spending */}
        <Card>
          <CardBody>
            <div className="space-y-2">
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                This Month
              </p>
              <p className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                ${summary?.monthly.toFixed(2) || '0.00'}
              </p>
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="text-[var(--color-text-secondary)]">
                    ${summary?.monthly_limit.toFixed(2) || '1000.00'} limit
                  </span>
                  <span className="text-[var(--color-text-secondary)] font-medium">
                    {monthlyUtilization.toFixed(0)}%
                  </span>
                </div>
                <div className="progress-track">
                  <div
                    className={clsx(
                      'progress-fill',
                      monthlyUtilization > 90 ? 'progress-error' :
                      monthlyUtilization > 70 ? 'progress-warning' : 'progress-success'
                    )}
                    style={{ width: `${Math.min(monthlyUtilization, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Total Spending */}
        <Card>
          <CardBody>
            <div className="space-y-2">
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                Total
              </p>
              <p className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                ${summary?.total.toFixed(2) || '0.00'}
              </p>
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                All time
              </p>
            </div>
          </CardBody>
        </Card>

        {/* Avg Cost Per Job */}
        <Card>
          <CardBody>
            <div className="space-y-2">
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                Avg per Job
              </p>
              <p className="text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                ${summary?.avg_cost_per_job.toFixed(2) || '0.00'}
              </p>
              <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                {summary?.completed_jobs || 0} completed
              </p>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Alert */}
      {(dailyUtilization > 80 || monthlyUtilization > 80) && (
        <div
          className="rounded-xl border p-4"
          style={{
            backgroundColor: 'var(--color-warning-subtle)',
            borderColor: 'var(--color-warning)',
          }}
        >
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 mt-0.5 flex-shrink-0"
              style={{ color: 'var(--color-warning)' }}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div className="space-y-1">
              <p className="text-sm font-semibold" style={{ color: 'var(--color-warning)' }}>
                Budget Alert
              </p>
              <div className="space-y-0.5 text-sm" style={{ color: 'var(--color-text-primary)' }}>
                {dailyUtilization > 80 && (
                  <p>Daily spending at {dailyUtilization.toFixed(0)}% of limit</p>
                )}
                {monthlyUtilization > 80 && (
                  <p>Monthly spending at {monthlyUtilization.toFixed(0)}% of limit</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
