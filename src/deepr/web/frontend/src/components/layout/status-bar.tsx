import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, DollarSign } from 'lucide-react'
import { cn } from '@/lib/utils'
import { jobsApi } from '@/api/jobs'
import { costApi } from '@/api/cost'
import { wsClient, type WebSocketStatus } from '@/api/websocket'
import { formatCurrency } from '@/lib/utils'

export default function StatusBar() {
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>(wsClient.status)

  useEffect(() => {
    setWsStatus(wsClient.status)
    const cleanup = wsClient.on('ws_status', (data: { status: WebSocketStatus }) => {
      setWsStatus(data.status)
    })
    return cleanup
  }, [])

  const { data: jobStats, isSuccess: jobsOk } = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: () => jobsApi.getStats(),
    refetchInterval: 15000,
  })

  const { data: costSummary, isSuccess: costOk } = useQuery({
    queryKey: ['cost', 'summary'],
    queryFn: () => costApi.getSummary(),
    refetchInterval: 60000,
  })

  // Online if WebSocket connected OR HTTP API responds
  const wsConnected = wsStatus === 'connected'
  const isOnline = wsConnected || jobsOk || costOk

  const activeJobs = (jobStats?.queued ?? 0) + (jobStats?.processing ?? 0)
  const todaySpend = costSummary?.daily ?? 0
  const connectionLabel = wsConnected
    ? 'Live updates connected'
    : isOnline && wsStatus === 'reconnecting'
      ? 'API online, live updates reconnecting'
      : isOnline
        ? 'API online, live updates unavailable'
        : 'Offline'

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
      <div role="status" className="flex items-center gap-1.5" title={connectionLabel}>
        <span
          aria-hidden="true"
          className={cn(
            'inline-block h-2 w-2 rounded-full',
            !isOnline
              ? 'bg-destructive'
              : wsConnected
                ? 'bg-green-500'
                : wsStatus === 'reconnecting'
                  ? 'bg-warning'
                  : 'bg-destructive'
          )}
        />
        <span>{connectionLabel}</span>
      </div>
    </div>
  )
}
