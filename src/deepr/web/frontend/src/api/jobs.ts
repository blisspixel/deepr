import apiClient from './client'
import type { Job, JobSubmitRequest, CostEstimate } from '../types'

export const jobsApi = {
  // Submit a new research job
  submit: async (data: JobSubmitRequest) => {
    const response = await apiClient.post<{ job: Job; estimated_cost: CostEstimate }>('/jobs', data)
    return response.data
  },

  // List all jobs
  list: async (params?: { status?: string; limit?: number; offset?: number }) => {
    const response = await apiClient.get<{ jobs: Job[]; total: number }>('/jobs', { params })
    return response.data
  },

  // Get job by ID
  get: async (jobId: string) => {
    const response = await apiClient.get<{ job: Job }>(`/jobs/${jobId}`)
    return response.data.job
  },

  // Cancel a job
  cancel: async (jobId: string) => {
    const response = await apiClient.post(`/jobs/${jobId}/cancel`)
    return response.data
  },

  // Delete a job
  delete: async (jobId: string) => {
    await apiClient.delete(`/jobs/${jobId}`)
  },

  // Submit multiple jobs
  batchSubmit: async (jobs: JobSubmitRequest[]) => {
    const response = await apiClient.post('/jobs/batch', { jobs })
    return response.data
  },

  // Bulk cancel jobs
  bulkCancel: async (jobIds: string[]) => {
    const response = await apiClient.post('/jobs/bulk-cancel', { job_ids: jobIds })
    return response.data
  },

  // Clean up stale PROCESSING/QUEUED jobs
  cleanupStale: async () => {
    const response = await apiClient.post<{ cleaned: number }>('/jobs/cleanup-stale')
    return response.data
  },

  // Get job queue stats
  getStats: async () => {
    const response = await apiClient.get<{
      total: number; queued: number; processing: number;
      completed: number; failed: number; cancelled: number;
      total_cost: number; total_tokens: number
    }>('/jobs/stats')
    return response.data
  },
}
