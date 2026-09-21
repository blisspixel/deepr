import test from 'node:test'
import assert from 'node:assert/strict'
import { parseExpertFormation } from '../src/lib/expert-formation.ts'

const record = { schema_version: 'deepr-formation-v1', status: 'running', stage: 'study', progress: 'Studying sources', updated_at: '2026-09-20T20:00:00Z', model_calls: 3, limitations: ['One publisher'] }
test('formation retains limits and does not infer qualification from completion', () => {
  assert.equal(parseExpertFormation(record).status, 'running')
  assert.deepEqual(parseExpertFormation({ ...record, status: 'research_complete' }).limitations, ['One publisher'])
})
test('malformed formation is an error instead of an empty expert', () => {
  for (const value of [null, {}, { ...record, status: 'qualified' }, { ...record, model_calls: -1 }, { ...record, limitations: [{}] }]) {
    assert.throws(() => parseExpertFormation(value))
  }
})
