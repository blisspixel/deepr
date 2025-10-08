import apiClient from './client'

export interface PlanRequest {
  scenario: string
  max_tasks?: number
  context?: string
  planner_model?: 'gpt-5' | 'gpt-5-mini' | 'gpt-5-nano' | 'gpt-5-chat'
  research_model?: string
  enable_web_search?: boolean
}

export interface PlannedTask {
  title: string
  prompt: string
  estimated_cost: number
}

export interface PlanResponse {
  plan: PlannedTask[]
  total_estimated_cost: number
  planner_model: string
  research_model: string
}

export interface ExecuteRequest {
  scenario: string
  tasks: Array<{ title: string; prompt: string }>
  model?: string
  priority?: number
  enable_web_search?: boolean
}

export interface ExecuteResponse {
  batch_id: string
  scenario: string
  jobs: Array<{
    id: string
    title: string
    prompt: string
    status: string
    estimated_cost: number
  }>
  total_jobs: number
  total_estimated_cost: number
}

export interface BatchStatus {
  batch_id: string
  scenario: string
  jobs: Array<{
    id: string
    title: string
    prompt: string
    status: string
    estimated_cost?: number
    actual_cost?: number
    created_at?: string
    updated_at?: string
  }>
  summary: {
    total: number
    pending: number
    in_progress: number
    completed: number
    failed: number
    total_cost: number
  }
}

export const plannerApi = {
  // Plan research strategy
  plan: async (request: PlanRequest) => {
    const response = await apiClient.post<PlanResponse>('/planner/plan', request)
    return response.data
  },

  // Execute research plan
  execute: async (request: ExecuteRequest) => {
    const response = await apiClient.post<ExecuteResponse>('/planner/execute', request)
    return response.data
  },

  // Get batch status
  getBatchStatus: async (batchId: string) => {
    const response = await apiClient.get<BatchStatus>(`/planner/batch/${batchId}`)
    return response.data
  },
}
