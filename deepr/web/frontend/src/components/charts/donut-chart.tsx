import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts'
import { CHART_COLORS, CHART_THEME } from '@/lib/chart-theme'

interface DonutChartProps {
  data: { name: string; value: number; color?: string }[]
  height?: number
  innerRadius?: number
  outerRadius?: number
  className?: string
  formatValue?: (value: number) => string
}

export function DonutChart({
  data,
  height = 200,
  innerRadius = 55,
  outerRadius = 80,
  className,
  formatValue = (v) => `$${v.toFixed(2)}`,
}: DonutChartProps) {
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            dataKey="value"
            strokeWidth={2}
            stroke="hsl(var(--background))"
          >
            {data.map((entry, index) => (
              <Cell
                key={entry.name}
                fill={entry.color || CHART_COLORS[index % CHART_COLORS.length]}
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: CHART_THEME.tooltip.background,
              border: `1px solid ${CHART_THEME.tooltip.border}`,
              borderRadius: CHART_THEME.tooltip.borderRadius,
              color: CHART_THEME.tooltip.text,
              fontSize: 13,
            }}
            formatter={(value: number) => [formatValue(value)]}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
