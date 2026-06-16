import { cn } from '@/lib/utils'
import { Check, Circle, Loader2 } from 'lucide-react'

export interface Phase {
  name: string
  status: 'completed' | 'active' | 'pending'
  duration?: string
}

interface ProgressPhasesProps {
  phases: Phase[]
  className?: string
}

export function ProgressPhases({ phases, className }: ProgressPhasesProps) {
  return (
    <div className={cn('flex items-center gap-1', className)}>
      {phases.map((phase, index) => (
        <div key={phase.name} className="flex items-center">
          {/* Phase indicator */}
          <div className="flex flex-col items-center">
            <div
              className={cn(
                'flex items-center justify-center w-8 h-8 rounded-full border-2 transition-colors',
                phase.status === 'completed' && 'bg-primary border-primary text-primary-foreground',
                phase.status === 'active' && 'border-primary text-primary',
                phase.status === 'pending' && 'border-muted-foreground/30 text-muted-foreground/30'
              )}
            >
              {phase.status === 'completed' && <Check className="w-4 h-4" />}
              {phase.status === 'active' && <Loader2 className="w-4 h-4 animate-spin" />}
              {phase.status === 'pending' && <Circle className="w-3 h-3" />}
            </div>
            <span
              className={cn(
                'text-xs mt-1.5 whitespace-nowrap',
                phase.status === 'active' && 'text-primary font-medium',
                phase.status === 'completed' && 'text-foreground',
                phase.status === 'pending' && 'text-muted-foreground/50'
              )}
            >
              {phase.name}
            </span>
            {phase.duration && (
              <span className="text-[10px] text-muted-foreground">{phase.duration}</span>
            )}
          </div>

          {/* Connector line */}
          {index < phases.length - 1 && (
            <div
              className={cn(
                'h-0.5 w-8 mx-1 mt-[-1.5rem]',
                phases[index + 1].status !== 'pending'
                  ? 'bg-primary'
                  : 'bg-muted-foreground/20'
              )}
            />
          )}
        </div>
      ))}
    </div>
  )
}
