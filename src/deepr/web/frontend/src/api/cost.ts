import apiClient from './client'
import type { CostSummary, CostEstimate, CostTrend } from '../types'

export const costApi = {
  // Get cost summary
  getSummary: async () => {
    const response = await apiClient.get<{ summary: CostSummary }>('/cost/summary')
    return response.data.summary
  },

  // Get spending trends
  getTrends: async (days = 30) => {
    const response = await apiClient.get<{ trends: { daily: CostTrend[]; cumulative: number } }>(
      '/cost/trends',
      { params: { days } }
    )
    return response.data.trends
  },

  // Get cost breakdown
  getBreakdown: async (timeRange: string = '30d') => {
    const response = await apiClient.get('/cost/breakdown', { params: { time_range: timeRange } })
    return response.data.breakdown
  },

  // Get cost history
  getHistory: async (timeRange: string = '30d') => {
    const response = await apiClient.get('/cost/history', { params: { time_range: timeRange } })
    return response.data.history
  },

  // Estimate cost
  estimate: async (data: { prompt: string; model?: string; enable_web_search?: boolean }) => {
    const response = await apiClient.post<{
      estimate: CostEstimate
      allowed: boolean
      reason?: string
    }>('/cost/estimate', data)
    return response.data
  },

  // Get budget limits
  getLimits: async () => {
    const response = await apiClient.get<{ limits: { per_job: number; daily: number; monthly: number } }>(
      '/cost/limits'
    )
    return response.data.limits
  },

  // Update budget limits
  updateLimits: async (limits: { per_job?: number; daily?: number; monthly?: number }) => {
    const response = await apiClient.patch('/cost/limits', limits)
    return response.data
  },
}
