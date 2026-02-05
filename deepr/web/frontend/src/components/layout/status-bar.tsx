import { useQuery } from '@tanstack/react-query'
import { Activity, DollarSign, Wifi, WifiOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { formatCurrency } from '@/lib/utils'

export default function StatusBar() {
  const { data: jobsData } = useQuery({
    queryKey: ['jobs', 'active'],
    queryFn: () => jobsApi.list({ status: 'processing' }),
    refetchInterval: 15000,
  })

  const { data: costSummary } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 60000,
  })

  const { isError: isOffline } = useQuery({
    queryKey: ['health'],
    queryFn: () => jobsApi.list({ limit: 1 }),
    refetchInterval: 30000,
    retry: false,
  })

  const activeJobs = jobsData?.jobs?.length ?? 0
  const todaySpend = costSummary?.daily ?? 0
  const isOnline = !isOffline

  return (
    <div className="flex h-8 items-center justify-between border-t bg-background px-4 text-[11px] text-muted-foreground">
      {/* Left section */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Activity className="h-3 w-3" />
          <span>
            {activeJobs} active job{activeJobs !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <DollarSign className="h-3 w-3" />
          <span>Today: {formatCurrency(todaySpend)}</span>
        </div>
      </div>

      {/* Right section */}
      <div className="flex items-center gap-1.5">
        {isOnline ? (
          <>
            <span
              className={cn(
                'inline-block h-2 w-2 rounded-full',
                'bg-green-500'
              )}
            />
            <Wifi className="h-3 w-3" />
            <span>Connected</span>
          </>
        ) : (
          <>
            <span
              className={cn(
                'inline-block h-2 w-2 rounded-full',
                'bg-destructive'
              )}
            />
            <WifiOff className="h-3 w-3" />
            <span>Offline</span>
          </>
        )}
      </div>
    </div>
  )
}
