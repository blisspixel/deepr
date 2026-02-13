import {
  ResponsiveContainer,
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { CHART_THEME } from '@/lib/chart-theme'

interface AreaChartProps {
  data: Record<string, unknown>[]
  dataKey: string
  xAxisKey: string
  color?: string
  height?: number
  showGrid?: boolean
  showAxis?: boolean
  formatTooltip?: (value: number) => string
  formatXAxis?: (value: string) => string
  className?: string
}

export function AreaChartComponent({
  data,
  dataKey,
  xAxisKey,
  color = 'hsl(var(--primary))',
  height = 300,
  showGrid = true,
  showAxis = true,
  formatTooltip,
  formatXAxis,
  className,
}: AreaChartProps) {
  if (!data?.length) {
    return (
      <div className={className} style={{ height }} />
    )
  }

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsAreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.2} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          {showGrid && (
            <CartesianGrid
              strokeDasharray={CHART_THEME.grid.strokeDasharray}
              stroke={CHART_THEME.grid.stroke}
              vertical={false}
            />
          )}
          {showAxis && (
            <>
              <XAxis
                dataKey={xAxisKey}
                tickFormatter={formatXAxis}
                tick={{ fontSize: 12, fill: CHART_THEME.axis.tick }}
                axisLine={{ stroke: CHART_THEME.axis.stroke }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: CHART_THEME.axis.tick }}
                axisLine={false}
                tickLine={false}
                width={50}
              />
            </>
          )}
          <Tooltip
            contentStyle={{
              backgroundColor: CHART_THEME.tooltip.background,
              border: `1px solid ${CHART_THEME.tooltip.border}`,
              borderRadius: CHART_THEME.tooltip.borderRadius,
              color: CHART_THEME.tooltip.text,
              fontSize: 13,
            }}
            formatter={formatTooltip ? (v: number) => [formatTooltip(v)] : undefined}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            fill="url(#areaGradient)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2 }}
          />
        </RechartsAreaChart>
      </ResponsiveContainer>
    </div>
  )
}
