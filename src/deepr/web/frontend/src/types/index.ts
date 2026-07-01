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
  cumulative: number
}

export interface Config {
  provider: string
  default_model: string
  default_priority: number
  enable_web_search: boolean
  storage: string
  queue: string
  has_api_key: boolean
  daily_limit: number
  monthly_limit: number
  provider_keys?: Record<string, boolean>
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
  portrait_url?: string | null
}

export type ExpertLoopRunStatus = 'pending' | 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled'

export interface ExpertLoopRun {
  schema_version: number
  run_id: string
  expert_name: string
  loop_type: string
  goal: string
  trigger: string
  status: ExpertLoopRunStatus
  started_at: string
  updated_at: string
  finished_at?: string | null
  iteration_count: number
  max_iterations?: number | null
  state_artifact_path: string
  budget_limit?: number | null
  budget_spent: number
  capacity_source: string
  backend_profile_id: string
  trace_id: string
  queue_id: string
  job_id: string
  approval_id: string
  input_refs: string[]
  output_refs: string[]
  knowledge_change_refs: string[]
  verifier_id: string
  verifier_version: string
  verifier_outcome: string
  verifier_score?: number | null
  verifier_threshold?: number | null
  verifier_evidence_refs: string[]
  accepted_changes: number
  rejected_changes: number
  acceptance_rate: number
  cost_per_accepted_change: number
  stop_reason?: string | null
  failure_reason: string
  next_action: Record<string, unknown>
}

export interface ExpertDashboardTelemetry {
  freshness: {
    is_stale: boolean
    status: string
    age_days?: number | null
    threshold_days?: number | null
    days_until_stale?: number | null
    domain_velocity: string
    urgency: string
    urgency_score: number
    estimated_refresh_cost: number
    last_refresh?: string | null
    knowledge_cutoff?: string | null
    message?: string | null
    action_required?: string | null
    refresh_command?: string | null
  }
  gaps: {
    total: number
    open: number
    closed: number
    opened_last_7_days: number
    closed_last_7_days: number
    opened_last_30_days: number
    closed_last_30_days: number
    net_open_delta_30_days: number
    top_open: {
      id: string
      topic: string
      priority: number
      ev_cost_ratio: number
      times_asked: number
      identified_at?: string | null
    }[]
  }
  contested_claims: {
    open_count: number
    manifest_claim_count: number
    belief_count: number
    contradiction_edge_count: number
    sample: {
      id: string
      domain: string
      updated_at?: string | null
      contradiction_count: number
    }[]
  }
}

export interface ExpertLoopAdmissionContract {
  loop_type: string
  status: 'admitted' | 'supervised'
  admitted: boolean
  repeat_demand: boolean
  automated_verification: boolean
  explicit_budget_capacity: boolean
  failure_diagnosis_state: boolean
  missing_requirements: string[]
  verifier: string
  notes: string
}

export interface ExpertLoopStatusRollup {
  expert_name: string
  count: number
  window: { limit: number; summarized_runs: number }
  latest_run: ExpertLoopRun | null
  last_sync_result: ExpertLoopRun | null
  last_failure: ExpertLoopRun | null
  next_scheduled_action: ExpertLoopRun | null
  latest_capacity_source: string
  status_counts: Record<ExpertLoopRunStatus, number>
  loop_type_counts: Record<string, number>
  stop_reason_counts: Record<string, number>
  capacity_source_counts: Record<string, number>
  budget_spent_total: number
  accepted_changes_total: number
  rejected_changes_total: number
  acceptance_rate: number
  cost_per_accepted_change: number
  verifier_failure_count: number
  admission_contracts: Record<string, ExpertLoopAdmissionContract>
  expert_state: ExpertDashboardTelemetry
  runs: ExpertLoopRun[]
}

export interface ExpertChat {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  id?: string
  session_id?: string
  cost?: number
  tool_calls?: { tool: string; query: string }[]
  follow_ups?: string[]
  confidence?: number
  error?: boolean
}

export interface ConversationSummary {
  session_id: string
  started_at: string
  message_count: number
  preview: string
  cost: number
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
  count: number
  tokens: number
  avg_cost: number
}

export interface CostAnomaly {
  date: string
  amount: number
  expected: number
  deviation: number
  message: string
}

// Benchmark types

export interface BenchmarkFile {
  filename: string
  timestamp: string
  tier_count: number
  model_count: number
  total_cost: number
}

export interface BenchmarkRanking {
  model_key: string
  avg_quality: number
  avg_latency_ms: number
  total_cost: number
  cost_per_quality: number
  scores_by_type: Record<string, number>
  num_evals: number
  errors: number
  tier: string
}

export interface BenchmarkResultEntry {
  model: string
  tier: string
  task_type: string
  difficulty: string
  quality: number
  judge_score: number
  reference_score: number
  citation_score: number
  citation_count: number
  report_length: number
  latency_ms: number
  error: string
}

export interface BenchmarkResult {
  timestamp: string
  total_cost: number
  rankings: BenchmarkRanking[]
  results: BenchmarkResultEntry[]
}

export interface RoutingPreferences {
  generated_at: string
  model_count: number
  task_preferences: Record<string, {
    best_quality: string
    best_quality_score: number
    best_value: string
    best_value_score: number
  }>
  overall_ranking: string[]
}

export interface RegistryModel {
  model_key: string
  provider: string
  model: string
  cost_per_query: number
  input_cost_per_1m: number
  output_cost_per_1m: number
  latency_ms: number
  context_window: number
  specializations: string[]
  strengths: string[]
  weaknesses: string[]
  deprecated: boolean
  successor?: string | null
}

// Contract types (canonical expert system types)

export type TrustClass = 'primary' | 'secondary' | 'tertiary' | 'self_generated'

export type SupportClass = 'supported' | 'partially_supported' | 'unsupported' | 'uncertain'

export interface Source {
  id: string
  url?: string
  title: string
  trust_class: TrustClass
  content_hash: string
  extraction_method: string
  retrieved_at: string
  support_class?: SupportClass
}

export interface Claim {
  id: string
  statement: string
  domain: string
  confidence: number
  sources: Source[]
  created_at: string
  updated_at: string
  contradicts: string[]
  supersedes?: string
  tags: string[]
}

export type DecisionType =
  | 'routing'
  | 'stop'
  | 'pivot'
  | 'budget'
  | 'belief_revision'
  | 'gap_fill'
  | 'conflict_resolution'
  | 'source_selection'

export interface DecisionRecord {
  id: string
  decision_type: DecisionType
  title: string
  rationale: string
  confidence: number
  alternatives: string[]
  evidence_refs: string[]
  cost_impact: number
  timestamp: string
  context: Record<string, unknown>
}

export interface ScoredGap {
  id: string
  topic: string
  questions: string[]
  priority: number
  estimated_cost: number
  expected_value: number
  ev_cost_ratio: number
  times_asked: number
  identified_at: string
  filled: boolean
  filled_at?: string
  filled_by_job?: string
}

export interface ExpertHistoryEvent {
  id: string
  type: string
  description: string
  timestamp: string
  cost?: number
}

export interface ExpertManifest {
  expert_name: string
  domain: string
  claims: Claim[]
  gaps: ScoredGap[]
  decisions: DecisionRecord[]
  policies: Record<string, unknown>
  generated_at: string
  claim_count: number
  open_gap_count: number
  avg_confidence: number
}

export interface SourceValidation {
  source_id: string
  claim_id: string
  support_class: SupportClass
  explanation: string
  validated_at: string
}

export interface ConsensusResult {
  query: string
  provider_responses: { provider: string; model: string; answer: string; cost: number }[]
  agreement_score: number
  consensus_answer: string
  confidence: number
  total_cost: number
  decision_record?: DecisionRecord
}

export interface Skill {
  name: string
  description: string
  version: string
  tools: number
  tier: 'built-in' | 'global' | 'expert-local'
  domains: string[]
  installed: boolean
}

// Agentic chat types

export type ChatMode = 'ask' | 'research' | 'advise' | 'focus'

export interface ChatCommandDef {
  name: string
  aliases: string[]
  description: string
  category: 'Mode' | 'Session' | 'Reasoning' | 'Control' | 'Management' | 'Utility'
  args: string
}

export interface CommandResult {
  success: boolean
  output: string
  clear_chat?: boolean
  end_session?: boolean
  mode?: ChatMode
  export_content?: string
  data?: Record<string, unknown>
}

export interface ThoughtItem {
  type: string
  text: string
  confidence: number | null
  phase: string | null
  timestamp: string
}

export interface PlanStep {
  id: number
  title: string
  query?: string
  depends_on?: number[]
  status: 'pending' | 'running' | 'done' | 'failed'
  result?: string
}

export interface ConfirmRequest {
  request_id: string
  tool_name: string
  query: string
  estimated_cost: number
  budget_remaining: number
}

export interface MemoryContext {
  conversations: number
  domains: { name: string; confidence: number }[]
  gaps: number
}

export interface CouncilResult {
  query: string
  perspectives: ExpertPerspective[]
  synthesis: string
  agreements: string[]
  disagreements: string[]
  total_cost: number
}

export interface ExpertPerspective {
  expert_name: string
  domain: string
  response: string
  confidence: number
  cost: number
}
