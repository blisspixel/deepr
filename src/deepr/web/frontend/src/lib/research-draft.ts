export const MAX_RESEARCH_PROMPT_LENGTH = 50_000

export type ResearchDraft = {
  version: 1
  prompt: string
  mode: string
  model: string
  priority: number
  enableWebSearch: boolean
}

export type DraftConstraints = {
  modes: readonly string[]
  models: readonly string[]
  priorities: readonly number[]
}

export type DraftLoadResult = {
  draft: ResearchDraft | null
  issue: 'discarded' | 'unavailable' | null
}

export type DraftStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
export type DraftStorageProvider = () => DraftStorage

export type InitialPromptResolution = {
  prompt: string
  pendingPrefill: string | null
  invalidPrefill: boolean
}

export function validateResearchPrompt(prompt: string): string | null {
  return prompt.length <= MAX_RESEARCH_PROMPT_LENGTH ? prompt : null
}

export function resolveInitialResearchPrompt(
  savedPrompt: string | null,
  queryPrompt: string | null,
): InitialPromptResolution {
  if (queryPrompt === null) {
    return { prompt: savedPrompt ?? '', pendingPrefill: null, invalidPrefill: false }
  }

  const validPrefill = validateResearchPrompt(queryPrompt)
  if (validPrefill === null) {
    return { prompt: savedPrompt ?? '', pendingPrefill: null, invalidPrefill: true }
  }
  if (savedPrompt && validPrefill && validPrefill !== savedPrompt) {
    return { prompt: savedPrompt, pendingPrefill: validPrefill, invalidPrefill: false }
  }
  return { prompt: validPrefill || savedPrompt || '', pendingPrefill: null, invalidPrefill: false }
}

export function isResearchDraft(
  value: unknown,
  constraints: DraftConstraints,
): value is ResearchDraft {
  if (!value || typeof value !== 'object') return false
  const draft = value as Record<string, unknown>
  return draft.version === 1
    && typeof draft.prompt === 'string'
    && validateResearchPrompt(draft.prompt) !== null
    && typeof draft.mode === 'string'
    && constraints.modes.includes(draft.mode)
    && typeof draft.model === 'string'
    && constraints.models.includes(draft.model)
    && typeof draft.priority === 'number'
    && constraints.priorities.includes(draft.priority)
    && typeof draft.enableWebSearch === 'boolean'
}

export function removeResearchDraft(
  key: string,
  storageProvider: DraftStorageProvider,
): boolean {
  try {
    storageProvider().removeItem(key)
    return true
  } catch {
    return false
  }
}

export function loadResearchDraft(
  key: string,
  storageProvider: DraftStorageProvider,
  constraints: DraftConstraints,
): DraftLoadResult {
  let rawDraft: string | null
  try {
    rawDraft = storageProvider().getItem(key)
  } catch {
    return { draft: null, issue: 'unavailable' }
  }

  if (!rawDraft) return { draft: null, issue: null }

  try {
    const draft: unknown = JSON.parse(rawDraft)
    if (isResearchDraft(draft, constraints)) return { draft, issue: null }
  } catch {
    // Invalid saved state is removed below and never reaches the form.
  }

  return removeResearchDraft(key, storageProvider)
    ? { draft: null, issue: 'discarded' }
    : { draft: null, issue: 'unavailable' }
}

export function saveResearchDraft(
  key: string,
  storageProvider: DraftStorageProvider,
  draft: ResearchDraft,
  constraints: DraftConstraints,
): boolean {
  const persistedDraft: ResearchDraft = {
    version: 1,
    prompt: draft.prompt,
    mode: draft.mode,
    model: draft.model,
    priority: draft.priority,
    enableWebSearch: draft.enableWebSearch,
  }
  if (!isResearchDraft(persistedDraft, constraints)) return false

  try {
    storageProvider().setItem(key, JSON.stringify(persistedDraft))
    return true
  } catch {
    return false
  }
}
