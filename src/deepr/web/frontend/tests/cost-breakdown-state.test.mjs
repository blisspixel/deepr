import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../src/pages/cost-intelligence.tsx', import.meta.url), 'utf8')

test('model spending distinguishes loading, query failure, and an empty ledger range', () => {
  assert.match(source, /isLoading: isBreakdownLoading/)
  assert.match(source, /isError: isBreakdownError/)
  assert.match(source, /Unable to load model spending from the cost ledger/)
  assert.match(source, /No model-attributed ledger events in this time range/)
  assert.doesNotMatch(source, /No spending data yet/)
})
