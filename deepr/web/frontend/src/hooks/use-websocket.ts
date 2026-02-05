import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsClient } from '@/api/websocket'
import type { Job } from '@/types'

export function useJobWebSocket() {
  const queryClient = useQueryClient()

  useEffect(() => {
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
      }),
      wsClient.on('cost_warning', () => {
        queryClient.invalidateQueries({ queryKey: ['cost'] })
      }),
    ]
    return () => cleanups.forEach(cleanup => cleanup())
  }, [queryClient])
}

export function useJobSubscription(jobId: string) {
  useEffect(() => {
    wsClient.subscribeToJobs(jobId)
    return () => wsClient.unsubscribeFromJobs(jobId)
  }, [jobId])
}
