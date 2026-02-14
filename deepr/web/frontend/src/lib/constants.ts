export const MODELS = [
  { value: 'o4-mini-deep-research', label: 'o4-mini', description: 'Faster, cheaper' },
  { value: 'o3-deep-research', label: 'o3', description: 'More thorough' },
] as const

export const PRIORITIES = [
  { value: 1, label: 'High' },
  { value: 3, label: 'Normal' },
  { value: 5, label: 'Low' },
] as const

export const RESEARCH_MODES = [
  { value: 'research', label: 'Research', description: 'Deep web research' },
  { value: 'check', label: 'Check', description: 'Fact verification' },
  { value: 'learn', label: 'Learn', description: 'Expert learning' },
  { value: 'team', label: 'Team', description: 'Multi-expert research' },
  { value: 'docs', label: 'Docs', description: 'Document analysis' },
] as const

export const JOB_STATUSES = {
  queued: { label: 'Queued', color: 'warning' },
  processing: { label: 'Running', color: 'info' },
  completed: { label: 'Completed', color: 'success' },
  failed: { label: 'Failed', color: 'destructive' },
  cancelled: { label: 'Cancelled', color: 'muted' },
} as const

export const TIME_RANGES = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
] as const

/** Default budget limits — used as fallbacks when backend is unreachable */
export const BUDGET_DEFAULTS = {
  PER_JOB: 20,
  DAILY: 100,
  MONTHLY: 1000,
} as const
