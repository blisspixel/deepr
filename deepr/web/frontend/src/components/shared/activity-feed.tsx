import {
  CheckCircle2,
  PlayCircle,
  XCircle,
  AlertTriangle,
  GraduationCap,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'

export type ActivityType =
  | 'job_completed'
  | 'job_started'
  | 'job_failed'
  | 'cost_warning'
  | 'expert_learned'

export interface ActivityItem {
  id: string
  type: ActivityType
  message: string
  timestamp: string
  status?: string
}

interface ActivityFeedProps {
  items: ActivityItem[]
  className?: string
}

const typeConfig: Record<ActivityType, { icon: LucideIcon; color: string }> = {
  job_completed: {
    icon: CheckCircle2,
    color: 'text-green-500',
  },
  job_started: {
    icon: PlayCircle,
    color: 'text-blue-500',
  },
  job_failed: {
    icon: XCircle,
    color: 'text-red-500',
  },
  cost_warning: {
    icon: AlertTriangle,
    color: 'text-yellow-500',
  },
  expert_learned: {
    icon: GraduationCap,
    color: 'text-purple-500',
  },
}

export default function ActivityFeed({ items, className }: ActivityFeedProps) {
  if (items.length === 0) {
    return (
      <div className={cn('py-8 text-center text-sm text-muted-foreground', className)}>
        No recent activity
      </div>
    )
  }

  return (
    <div className={cn('space-y-1', className)}>
      {items.map((item) => {
        const config = typeConfig[item.type]
        const Icon = config.icon

        return (
          <div
            key={item.id}
            className="flex items-start gap-3 rounded-md px-3 py-2.5 transition-colors hover:bg-muted/50"
          >
            <div className={cn('mt-0.5 shrink-0', config.color)}>
              <Icon className="h-4 w-4" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-sm leading-snug text-foreground">
                {item.message}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {formatRelativeTime(item.timestamp)}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
