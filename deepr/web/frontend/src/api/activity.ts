import apiClient from './client'
import type { ActivityItem } from '../types'

export const activityApi = {
  list: async (limit = 20) => {
    const response = await apiClient.get<{ items: ActivityItem[] }>('/activity', { params: { limit } })
    return response.data.items
  },
}
