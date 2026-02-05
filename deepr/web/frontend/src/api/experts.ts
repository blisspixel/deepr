import apiClient from './client'
import type { Expert, ExpertChat, KnowledgeGap } from '../types'

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
    const response = await apiClient.get<{ gaps: KnowledgeGap[] }>(`/experts/${name}/gaps`)
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
}
