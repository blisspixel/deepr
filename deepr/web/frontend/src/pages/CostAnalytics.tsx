import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    ${summary?.daily_limit.toFixed(2) || '100.00'} limit
                  </span>
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    {dailyUtilization.toFixed(0)}%
                  </span>
                </div>
                <div className="w-full rounded-full h-1" style={{ backgroundColor: 'var(--color-border)' }}>
                  <div
                    className="h-1 rounded-full"
                    style={{
                      width: `${Math.min(dailyUtilization, 100)}%`,
                      backgroundColor: 'var(--color-text-primary)'
                    }}
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
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    ${summary?.monthly_limit.toFixed(2) || '1000.00'} limit
                  </span>
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    {monthlyUtilization.toFixed(0)}%
                  </span>
                </div>
                <div className="w-full rounded-full h-1" style={{ backgroundColor: 'var(--color-border)' }}>
                  <div
                    className="h-1 rounded-full"
                    style={{
                      width: `${Math.min(monthlyUtilization, 100)}%`,
                      backgroundColor: 'var(--color-text-primary)'
                    }}
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
        <Card>
          <CardBody>
            <div className="space-y-2">
              <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                Budget Alert
              </p>
              <div className="space-y-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                {dailyUtilization > 80 && (
                  <p>
                    Daily spending at {dailyUtilization.toFixed(0)}% of limit
                  </p>
                )}
                {monthlyUtilization > 80 && (
                  <p>
                    Monthly spending at {monthlyUtilization.toFixed(0)}% of limit
                  </p>
                )}
              </div>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
