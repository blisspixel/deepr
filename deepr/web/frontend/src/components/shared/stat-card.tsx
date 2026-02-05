import type { LucideIcon } from 'lucide-react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'

type TrendDirection = 'up' | 'down' | 'neutral'

interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  trend?: TrendDirection
  trendValue?: string
  icon?: LucideIcon
  className?: string
}

export default function StatCard({
  title,
  value,
  subtitle,
  trend,
  trendValue,
  icon: Icon,
  className,
}: StatCardProps) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus

  return (
    <Card className={cn('relative overflow-hidden', className)}>
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold tracking-tight">{value}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
          </div>

          {Icon && (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon className="h-5 w-5" />
            </div>
          )}
        </div>

        {/* Trend indicator */}
        {trend && trendValue && (
          <div className="mt-3 flex items-center gap-1.5">
            <div
              className={cn(
                'flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-medium',
                trend === 'up' && 'bg-green-500/10 text-green-600 dark:text-green-400',
                trend === 'down' && 'bg-red-500/10 text-red-600 dark:text-red-400',
                trend === 'neutral' && 'bg-muted text-muted-foreground'
              )}
            >
              <TrendIcon className="h-3 w-3" />
              <span>{trendValue}</span>
            </div>
          </div>
        )}

        {/* Sparkline placeholder */}
        <div className="mt-4 h-8 w-full rounded bg-muted/30" />
      </CardContent>
    </Card>
  )
}
