import apiClient from './client'

export interface Config {
  // General
  default_model: string
  default_priority: number
  enable_web_search: boolean

  // API
  openai_api_key: string
  azure_api_key: string
  azure_endpoint: string

  // Limits
  daily_limit: number
  monthly_limit: number
  max_concurrent_jobs: number

  // Storage
  storage_type: 'local' | 'azure'
  azure_connection_string: string
}

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
}
