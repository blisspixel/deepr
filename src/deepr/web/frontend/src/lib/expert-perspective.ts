export interface ExpertPosition {
  question: string
  stance: string
  reasoning: string
  would_change_my_mind: string
  unresolved_dissent: string
  confidence_basis: string
  supported_by: string[]
}

export interface ExpertPerspective {
  orientation: string
  positions: ExpertPosition[]
  state: { settled: string[]; live: string[]; unknown: string[] }
  anticipated_questions: { question: string; answer: string }[]
  limitations: string[]
}

export interface ExpertFinding {
  finding_id: string
  title: string
  anchors: string[]
  corpus_shas: string[]
  is_grounded: boolean
}

export interface ExpertStudy {
  started_at: string
  findings: ExpertFinding[]
  limitations: string[]
}

export interface ExpertSource {
  sha256: string
  title: string
  url: string
  publisher: string
  added_at: string
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('The retained expert record is malformed.')
  }
  return value as Record<string, unknown>
}

function records(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) throw new Error('The retained expert list is malformed.')
  return value.map(record)
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function texts(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function parseExpertPerspective(value: unknown): ExpertPerspective {
  const brief = record(value)
  const state = record(brief.state ?? {})
  return {
    orientation: text(brief.orientation),
    positions: records(brief.positions).map((position) => ({
      question: text(position.question),
      stance: text(position.stance),
      reasoning: text(position.reasoning),
      would_change_my_mind: text(position.would_change_my_mind),
      unresolved_dissent: text(position.unresolved_dissent),
      confidence_basis: text(position.confidence_basis),
      supported_by: texts(position.supported_by),
    })),
    state: { settled: texts(state.settled), live: texts(state.live), unknown: texts(state.unknown) },
    anticipated_questions: records(brief.anticipated_questions ?? []).map((question) => ({
      question: text(question.question), answer: text(question.answer),
    })),
    limitations: texts(brief.limitations),
  }
}

export function parseExpertStudy(value: unknown): ExpertStudy {
  const study = record(value)
  return {
    started_at: text(study.started_at),
    findings: records(study.outcomes).flatMap((outcome) => records(outcome.findings).map((finding) => ({
      finding_id: text(finding.finding_id), title: text(finding.title),
      anchors: texts(finding.anchors), corpus_shas: texts(finding.corpus_shas),
      is_grounded: finding.is_grounded === true,
    }))),
    limitations: texts(study.limitations),
  }
}

export function parseExpertSources(value: unknown): ExpertSource[] {
  // Historical findings may refer to superseded sources. Keep the complete
  // retained inventory for citation resolution instead of only current sources.
  return records(record(value).sources).map((source) => ({
    sha256: text(source.sha256), title: text(source.title), url: text(source.url),
    publisher: text(source.publisher), added_at: text(source.added_at),
  }))
}

export function expertSourceUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch {
    return null
  }
}

export function expertStudyDate(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return null
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}
