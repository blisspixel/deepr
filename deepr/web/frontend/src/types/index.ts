export interface Job {
  id: string
  prompt: string
  model: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  priority: number
  enable_web_search: boolean
  file_ids?: string[]
  estimated_cost?: number
  actual_cost?: number
  created_at: string
  updated_at: string
  provider_job_id?: string
}

export interface Result {
  id: string
  job_id: string
  prompt: string
  model: string
  title?: string
  content: string
  citations?: Citation[]
  citations_count: number
  metadata?: Record<string, any>
  completed_at: string
  created_at: string
  cost: number
  enable_web_search: boolean
  tags?: string[]
}

export interface Citation {
  url?: string
  title: string
  snippet?: string
  start_index?: number
  end_index?: number
}

export interface CostEstimate {
  expected_cost: number
  min_cost: number
  max_cost: number
}

export interface CostSummary {
  daily: number
  daily_limit: number
  monthly: number
  monthly_limit: number
  total: number
  avg_per_job: number
  total_jobs: number
}

export interface CostTrend {
  date: string
  cost: number
  jobs: number
}

export interface Config {
  provider: string
  default_model: string
  enable_web_search: boolean
  storage: string
  queue: string
  has_api_key: boolean
}

export interface SystemStatus {
  healthy: boolean
  version: string
  provider: string
  queue: {
    type: string
    stats: {
      pending: number
      in_progress: number
      completed: number
      failed: number
    }
  }
  spending: CostSummary
}

export interface JobSubmitRequest {
  prompt: string
  model?: string
  priority?: number
  enable_web_search?: boolean
  file_ids?: string[]
  config?: Record<string, any>
}

export interface ApiError {
  error: string
  message?: string
}
