import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAX_RESEARCH_PROMPT_LENGTH,
  loadResearchDraft,
  removeResearchDraft,
  resolveInitialResearchPrompt,
  saveResearchDraft,
  validateResearchPrompt,
} from '../src/lib/research-draft.ts'

const KEY = 'draft'
const CONSTRAINTS = {
  modes: ['research', 'check'],
  models: ['o4-mini-deep-research'],
  priorities: [1, 3, 5],
}
const VALID_DRAFT = {
  version: 1,
  prompt: 'Compare public evidence.',
  mode: 'research',
  model: 'o4-mini-deep-research',
  priority: 1,
  enableWebSearch: true,
}

function memoryStorage(initialValue = null) {
  let value = initialValue
  return {
    getItem: () => value,
    setItem: (_key, nextValue) => { value = nextValue },
    removeItem: () => { value = null },
    value: () => value,
  }
}

test('restores a valid scalar-only draft', () => {
  const storage = memoryStorage(JSON.stringify(VALID_DRAFT))

  assert.deepEqual(loadResearchDraft(KEY, () => storage, CONSTRAINTS), {
    draft: VALID_DRAFT,
    issue: null,
  })
})

test('discards invalid JSON and invalid schema', () => {
  for (const value of ['{invalid', JSON.stringify({ ...VALID_DRAFT, mode: 'unknown' })]) {
    const storage = memoryStorage(value)

    assert.deepEqual(loadResearchDraft(KEY, () => storage, CONSTRAINTS), {
      draft: null,
      issue: 'discarded',
    })
    assert.equal(storage.value(), null)
  }
})

test('reports unavailable storage without throwing', () => {
  const deniedStorage = () => { throw new Error('denied') }

  assert.deepEqual(loadResearchDraft(KEY, deniedStorage, CONSTRAINTS), {
    draft: null,
    issue: 'unavailable',
  })
  assert.equal(saveResearchDraft(KEY, deniedStorage, VALID_DRAFT, CONSTRAINTS), false)
  assert.equal(removeResearchDraft(KEY, deniedStorage), false)
})

test('saves only the explicit draft schema and clears it', () => {
  const storage = memoryStorage()
  const source = {
    ...VALID_DRAFT,
    uploadedFiles: [{ name: 'private.txt' }],
    uploadedFileContents: [{ name: 'private.txt', content: 'secret' }],
  }
  assert.equal(saveResearchDraft(KEY, () => storage, source, CONSTRAINTS), true)
  assert.deepEqual(JSON.parse(storage.value()), VALID_DRAFT)
  assert.equal(removeResearchDraft(KEY, () => storage), true)
  assert.equal(storage.value(), null)
})

test('refuses to persist invalid runtime state', () => {
  const storage = memoryStorage()

  assert.equal(
    saveResearchDraft(KEY, () => storage, { ...VALID_DRAFT, mode: 'unknown' }, CONSTRAINTS),
    false,
  )
  assert.equal(storage.value(), null)
})

test('rejects prompts above the shared input limit', () => {
  assert.equal(validateResearchPrompt('x'.repeat(MAX_RESEARCH_PROMPT_LENGTH)), 'x'.repeat(MAX_RESEARCH_PROMPT_LENGTH))
  assert.equal(validateResearchPrompt('x'.repeat(MAX_RESEARCH_PROMPT_LENGTH + 1)), null)
})

test('preserves a saved draft until a different URL prefill is accepted', () => {
  assert.deepEqual(resolveInitialResearchPrompt('saved prompt', 'linked prompt'), {
    prompt: 'saved prompt',
    pendingPrefill: 'linked prompt',
    invalidPrefill: false,
  })
  assert.deepEqual(resolveInitialResearchPrompt(null, 'linked prompt'), {
    prompt: 'linked prompt',
    pendingPrefill: null,
    invalidPrefill: false,
  })
})

test('rejects an oversized URL prefill without discarding a saved draft', () => {
  assert.deepEqual(
    resolveInitialResearchPrompt('saved prompt', 'x'.repeat(MAX_RESEARCH_PROMPT_LENGTH + 1)),
    { prompt: 'saved prompt', pendingPrefill: null, invalidPrefill: true },
  )
})
