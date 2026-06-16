import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsClient } from '@/api/websocket'
import { useNotificationStore } from '@/stores/notification-store'
import type { Job } from '@/types'

export function useJobWebSocket() {
  const queryClient = useQueryClient()
  const { setFailedJobCount } = useNotificationStore()

  useEffect(() => {
    // Seed the failed count from the initial jobs query cache when it arrives
    const unsub = queryClient.getQueryCache().subscribe((event) => {
      if (event?.query?.queryKey?.[0] === 'jobs' && event.type === 'updated') {
        const data = event.query.state.data as { jobs?: Job[] } | undefined
        if (data?.jobs) {
          setFailedJobCount(data.jobs.filter((j) => j.status === 'failed').length)
        }
      }
    })

    const cleanups = [
      wsClient.on('job_created', (_job: Job) => {
        queryClient.invalidateQueries({ queryKey: ['jobs'] })
      }),
      wsClient.on('job_updated', (job: Job) => {
        queryClient.invalidateQueries({ queryKey: ['jobs'] })
        queryClient.invalidateQueries({ queryKey: ['jobs', job.id] })
      }),
      wsClient.on('job_completed', (_job: Job) => {
        queryClient.invalidateQueries({ queryKey: ['jobs'] })
        queryClient.invalidateQueries({ queryKey: ['results'] })
        queryClient.invalidateQueries({ queryKey: ['cost'] })
      }),
      wsClient.on('job_failed', () => {
        queryClient.invalidateQueries({ queryKey: ['jobs'] })
        useNotificationStore.setState((s) => ({ failedJobCount: s.failedJobCount + 1 }))
      }),
      wsClient.on('cost_warning', () => {
        queryClient.invalidateQueries({ queryKey: ['cost'] })
      }),
    ]
    return () => {
      unsub()
      cleanups.forEach(cleanup => cleanup())
    }
  }, [queryClient, setFailedJobCount])
}

export function useJobSubscription(jobId: string) {
  useEffect(() => {
    wsClient.subscribeToJobs(jobId)
    return () => wsClient.unsubscribeFromJobs(jobId)
  }, [jobId])
}
