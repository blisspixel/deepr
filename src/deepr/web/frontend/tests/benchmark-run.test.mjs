import assert from 'node:assert/strict'
import test from 'node:test'

import {
  benchmarkOptionsMatch,
  confirmedBenchmarkOptions,
  registryFailureBlocksSurface,
  snapshotBenchmarkEstimate,
  verifiedProviderKeys,
} from '../src/lib/benchmark-run.ts'

const OPTIONS = { tier: 'research', quick: false, no_judge: false }
const ESTIMATE = {
  estimated_cost: 1.25,
  model_count: 3,
  provider_count: 2,
  tier: 'research',
}

test('snapshots the exact options that produced an estimate', () => {
  const source = { ...OPTIONS }
  const snapshot = snapshotBenchmarkEstimate(ESTIMATE, source)

  source.quick = true
  assert.deepEqual(snapshot.options, OPTIONS)
})

test('invalidates approval when any paid-run option changes', () => {
  for (const changed of [
    { ...OPTIONS, tier: 'chat' },
    { ...OPTIONS, quick: true },
    { ...OPTIONS, no_judge: true },
  ]) {
    assert.equal(benchmarkOptionsMatch(OPTIONS, changed), false)
    assert.equal(
      confirmedBenchmarkOptions(snapshotBenchmarkEstimate(ESTIMATE, OPTIONS), changed),
      null,
    )
  }
})

test('dispatches a copy of only the approved options', () => {
  const snapshot = snapshotBenchmarkEstimate(ESTIMATE, OPTIONS)
  const confirmed = confirmedBenchmarkOptions(snapshot, OPTIONS)

  assert.deepEqual(confirmed, { ...OPTIONS, max_estimated_cost: ESTIMATE.estimated_cost })
  assert.notEqual(confirmed, snapshot.options)
})

test('fails provider readiness closed when cached configuration refresh fails', () => {
  const cached = { openai: true }

  assert.equal(verifiedProviderKeys(cached, true), undefined)
  assert.equal(verifiedProviderKeys(cached, false), cached)
})

test('blocks the models surface when registry loading fails without other evidence', () => {
  assert.equal(registryFailureBlocksSurface(true, false, false), true)
  assert.equal(registryFailureBlocksSurface(true, true, false), false)
  assert.equal(registryFailureBlocksSurface(true, false, true), false)
})
