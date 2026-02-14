import apiClient from './client'
import type { BenchmarkFile, BenchmarkResult, RoutingPreferences, RegistryModel } from '../types'

export const benchmarksApi = {
  list: async () => {
    const response = await apiClient.get<{ benchmarks: BenchmarkFile[] }>('/benchmarks')
    return response.data.benchmarks
  },

  getLatest: async () => {
    const response = await apiClient.get<{ result: BenchmarkResult | null; filename?: string }>(
      '/benchmarks/latest'
    )
    return response.data
  },

  get: async (filename: string) => {
    const response = await apiClient.get<{ result: BenchmarkResult; filename: string }>(
      `/benchmarks/${filename}`
    )
    return response.data
  },

  start: async (opts: { tier?: string; quick?: boolean; no_judge?: boolean }) => {
    const response = await apiClient.post<{ status: string; started_at: string }>(
      '/benchmarks/start',
      opts
    )
    return response.data
  },

  getStatus: async () => {
    const response = await apiClient.get<{
      status: 'idle' | 'running' | 'completed' | 'failed'
      started_at?: string
      exit_code?: number | null
      output_lines?: string[]
    }>('/benchmarks/status')
    return response.data
  },

  getRouting: async () => {
    const response = await apiClient.get<{ preferences: RoutingPreferences | null }>(
      '/benchmarks/routing-preferences'
    )
    return response.data.preferences
  },

  getRegistry: async () => {
    const response = await apiClient.get<{ models: RegistryModel[] }>('/models/registry')
    return response.data.models
  },
}
