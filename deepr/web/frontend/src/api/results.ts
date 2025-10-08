import apiClient from './client'
import type { Result } from '../types'

export const resultsApi = {
  // List all results
  list: async (params?: {
    search?: string
    tags?: string
    limit?: number
    offset?: number
    sort_by?: string
    order?: string
  }) => {
    const response = await apiClient.get<{ results: Result[]; total: number }>('/results', { params })
    return response.data
  },

  // Get result by job ID
  get: async (jobId: string) => {
    const response = await apiClient.get<{ result: Result }>(`/results/${jobId}`)
    return response.data.result
  },

  // Get result by job ID (alias for consistency)
  getById: async (jobId: string) => {
    const response = await apiClient.get<{ result: Result }>(`/results/${jobId}`)
    return response.data.result
  },

  // Export result in various formats
  export: async (jobId: string, format: 'markdown' | 'pdf' | 'json') => {
    const response = await apiClient.get(`/results/${jobId}/export/${format}`, {
      responseType: 'blob',
    })
    return response.data
  },

  // Download result
  download: async (jobId: string, format: 'md' | 'docx' | 'txt' | 'json' | 'pdf') => {
    const response = await apiClient.get(`/results/${jobId}/download/${format}`, {
      responseType: 'blob',
    })
    return response.data
  },

  // Search results
  search: async (query: string, limit = 20) => {
    const response = await apiClient.get<{ results: Result[]; total: number }>('/results/search', {
      params: { q: query, limit },
    })
    return response.data
  },

  // Add tags
  addTags: async (jobId: string, tags: string[]) => {
    const response = await apiClient.post(`/results/${jobId}/tags`, { tags })
    return response.data
  },

  // Remove tag
  removeTag: async (jobId: string, tag: string) => {
    await apiClient.delete(`/results/${jobId}/tags/${tag}`)
  },
}
