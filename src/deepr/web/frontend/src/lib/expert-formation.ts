export type ExpertFormation = {
  status: 'running' | 'research_complete' | 'incomplete' | 'interrupted'
  stage: string
  progress: string
  updated_at: string
  model_calls: number
  limitations: string[]
}

export function parseExpertFormation(value: unknown): ExpertFormation {
  if (!value || typeof value !== 'object') throw new Error('Invalid formation record.')
  const record = value as Record<string, unknown>
  const statuses = ['running', 'research_complete', 'incomplete', 'interrupted']
  if (record.schema_version !== 'deepr-formation-v1' || !statuses.includes(String(record.status)) ||
      typeof record.stage !== 'string' || typeof record.progress !== 'string' || typeof record.updated_at !== 'string' ||
      typeof record.model_calls !== 'number' || !Number.isInteger(record.model_calls) || record.model_calls < 0) {
    throw new Error('Invalid formation record.')
  }
  const limitations = record.limitations ?? []
  if (!Array.isArray(limitations) || limitations.some(item => typeof item !== 'string')) throw new Error('Invalid formation limitations.')
  return { status: record.status as ExpertFormation['status'], stage: record.stage, progress: record.progress,
    updated_at: record.updated_at, model_calls: record.model_calls, limitations }
}
