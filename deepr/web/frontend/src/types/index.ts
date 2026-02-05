export interface Job {
  id: string
  prompt: string
  model: string
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
  priority: number
  enable_web_search?: boolean
  file_ids?: string[]
  cost: number
  tokens_used: number
  submitted_at: string
  started_at?: string
  completed_at?: string
  provider_job_id?: string
  last_error?: string
  metadata?: Record<string, unknown>
  result?: string
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
  per_job_limit: number
  avg_cost_per_job: number
  completed_jobs: number
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
  mode?: string
  priority?: number
  enable_web_search?: boolean
  file_ids?: string[]
  config?: Record<string, any>
}

export interface ApiError {
  error: string
  message?: string
}

export type ResearchMode = 'research' | 'check' | 'learn' | 'team' | 'docs'

export interface Expert {
  name: string
  description: string
  document_count: number
  finding_count: number
  gap_count: number
  total_cost: number
  last_active: string
  created_at: string
}

export interface ExpertChat {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface KnowledgeGap {
  id: string
  topic: string
  description: string
  priority: 'high' | 'medium' | 'low'
  created_at: string
}

export interface TraceSpan {
  id: string
  name: string
  parent_id?: string
  start_time: number
  end_time: number
  duration_ms: number
  status: 'completed' | 'failed' | 'running'
  cost: number
  tokens: number
  model?: string
  metadata?: Record<string, unknown>
  children?: TraceSpan[]
}

export interface TraceData {
  job_id: string
  root_span: TraceSpan
  total_duration_ms: number
  total_cost: number
  total_tokens: number
}

export interface TemporalFinding {
  timestamp: number
  type: 'fact' | 'hypothesis' | 'contradiction'
  content: string
  confidence: number
  confidence_change?: 'up' | 'down'
}

export interface ActivityItem {
  id: string
  type: 'job_completed' | 'job_started' | 'job_failed' | 'cost_warning' | 'expert_learned'
  message: string
  timestamp: string
  metadata?: Record<string, unknown>
}

export interface CostBreakdown {
  model: string
  cost: number
  percentage: number
  job_count: number
}

export interface CostAnomaly {
  date: string
  amount: number
  expected: number
  deviation: number
  message: string
}
