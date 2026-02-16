import apiClient from './client'
import type { Expert, ExpertChat, ExpertHistoryEvent, ExpertManifest, Claim, DecisionRecord, ScoredGap, SourceValidation } from '../types'

export const expertsApi = {
  list: async () => {
    const response = await apiClient.get<{ experts: Expert[] }>('/experts')
    return response.data.experts
  },
  create: async (data: { name: string; description?: string; domain?: string }) => {
    const response = await apiClient.post<{ expert: Expert }>('/experts', data)
    return response.data.expert
  },
  get: async (name: string) => {
    const response = await apiClient.get<{ expert: Expert }>(`/experts/${name}`)
    return response.data.expert
  },
  chat: async (name: string, message: string) => {
    const response = await apiClient.post<{ response: ExpertChat }>(`/experts/${name}/chat`, { message })
    return response.data.response
  },
  getGaps: async (name: string) => {
    const response = await apiClient.get<{ gaps: ScoredGap[] }>(`/experts/${name}/gaps`)
    return response.data.gaps
  },
  getHistory: async (name: string) => {
    const response = await apiClient.get<{ events: ExpertHistoryEvent[] }>(`/experts/${name}/history`)
    return response.data.events
  },
  getManifest: async (name: string) => {
    const response = await apiClient.get<{ manifest: ExpertManifest }>(`/experts/${name}/manifest`)
    return response.data.manifest
  },
  getClaims: async (name: string, params?: { domain?: string; min_confidence?: number }) => {
    const response = await apiClient.get<{ claims: Claim[] }>(`/experts/${name}/claims`, { params })
    return response.data.claims
  },
  getDecisions: async (name: string, params?: { type?: string; job_id?: string; limit?: number }) => {
    const response = await apiClient.get<{ decisions: DecisionRecord[] }>(`/experts/${name}/decisions`, { params })
    return response.data.decisions
  },
  fillGaps: async (name: string, data: { consensus?: boolean; deep?: boolean; top?: number; budget?: number; validate_citations?: boolean }) => {
    const response = await apiClient.post<{ filled: number; total_gaps: number }>(`/experts/${name}/fill-gaps`, data)
    return response.data
  },
  getCitationValidations: async (name: string) => {
    const response = await apiClient.get<{ validations: SourceValidation[]; summary: Record<string, number | string[]> }>(`/experts/${name}/citation-validations`)
    return response.data
  },
  discoverGaps: async (name: string) => {
    const response = await apiClient.post<{ gaps: Record<string, unknown>[] }>(`/experts/${name}/discover-gaps`)
    return response.data.gaps
  },
  resolveConflicts: async (name: string, data?: { budget?: number }) => {
    const response = await apiClient.post<{ results: Record<string, unknown>[] }>(`/experts/${name}/resolve-conflicts`, data)
    return response.data.results
  },
}
