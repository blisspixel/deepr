import apiClient from './client'

export const tracesApi = {
  get: async (jobId: string) => {
    const response = await apiClient.get(`/traces/${jobId}`)
    return response.data.trace
  },
  getTemporal: async (jobId: string) => {
    const response = await apiClient.get(`/traces/${jobId}/temporal`)
    return response.data.findings
  },
}
