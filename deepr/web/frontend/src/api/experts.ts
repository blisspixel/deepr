import apiClient from './client'
import type { Expert, ExpertChat, ExpertManifest, Claim, DecisionRecord, ScoredGap } from '../types'

export const expertsApi = {
  list: async () => {
    const response = await apiClient.get<{ experts: Expert[] }>('/experts')
    return response.data.experts
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
  learnGap: async (name: string, gapId: string) => {
    const response = await apiClient.post(`/experts/${name}/learn`, { gap_id: gapId })
    return response.data
  },
  getHistory: async (name: string) => {
    const response = await apiClient.get(`/experts/${name}/history`)
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
}
