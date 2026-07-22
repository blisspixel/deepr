import axios from 'axios'
import {
  ApiRequestError,
  DASHBOARD_AUTH_REQUIRED_EVENT,
  extractDashboardBearerToken,
  loadDashboardToken,
  type DashboardAuthRequiredDetail,
} from '@/lib/dashboard-auth'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    const token = loadDashboardToken()
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const responseMessage = error.response.data?.message || error.response.data?.error
      const message = typeof responseMessage === 'string' ? responseMessage : 'An error occurred'
      const errorCode = typeof error.response.data?.error_code === 'string'
        ? error.response.data.error_code
        : null
      const status = typeof error.response.status === 'number' ? error.response.status : null
      if (status === 401 && typeof window !== 'undefined') {
        const token = extractDashboardBearerToken(error.config?.headers)
        window.dispatchEvent(new CustomEvent<DashboardAuthRequiredDetail>(
          DASHBOARD_AUTH_REQUIRED_EVENT,
          { detail: { token } },
        ))
      }
      return Promise.reject(new ApiRequestError(message, { status, errorCode, hasResponse: true }))
    } else if (error.request) {
      return Promise.reject(new ApiRequestError('No response from server'))
    } else {
      // Request setup error
      return Promise.reject(error)
    }
  }
)

export default apiClient
