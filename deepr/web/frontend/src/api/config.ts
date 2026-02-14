import apiClient from './client'
import type { Config } from '../types'

export const configApi = {
  // Get current configuration
  get: async () => {
    const response = await apiClient.get<{ config: Config }>('/config')
    return response.data.config
  },

  // Update configuration
  update: async (updates: Partial<Config>) => {
    const response = await apiClient.patch<{ config: Config }>('/config', updates)
    return response.data.config
  },

  // Test API connection
  testConnection: async (provider: 'openai' | 'azure') => {
    const response = await apiClient.post<{ success: boolean; message: string }>(
      '/config/test-connection',
      { provider }
    )
    return response.data
  },

  // Load demo data (experts + sample jobs)
  loadDemo: async () => {
    const response = await apiClient.post<{ success: boolean; created_jobs: number; errors: string[] }>(
      '/demo/load'
    )
    return response.data
  },
}
