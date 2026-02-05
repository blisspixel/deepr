export const CHART_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
  'hsl(var(--chart-6))',
  'hsl(var(--chart-7))',
  'hsl(var(--chart-8))',
] as const

export const CHART_THEME = {
  axis: {
    stroke: 'hsl(var(--border))',
    tick: 'hsl(var(--muted-foreground))',
    fontSize: 12,
  },
  grid: {
    stroke: 'hsl(var(--border))',
    strokeDasharray: '3 3',
  },
  tooltip: {
    background: 'hsl(var(--popover))',
    border: 'hsl(var(--border))',
    text: 'hsl(var(--popover-foreground))',
    borderRadius: 8,
  },
  area: {
    fillOpacity: 0.15,
  },
} as const
