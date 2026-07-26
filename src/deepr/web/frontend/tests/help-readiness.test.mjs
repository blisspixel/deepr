import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('dashboard Help presents only current safe quick-reference paths', async () => {
  const source = await readFile(new URL('../src/pages/help.tsx', import.meta.url), 'utf8')

  assert.match(source, /deepr doctor --skip-connectivity/)
  assert.match(source, /deepr capacity next --task-class sync/)
  assert.match(source, /deepr expert make my-expert --local/)
  assert.match(source, /deepr expert consult "what should change\?" -e my-expert --local/)
  assert.match(source, /deepr mcp serve/)
  assert.doesNotMatch(source, /deepr expert chat my-expert/)
  assert.doesNotMatch(source, /\{ cmd: 'deepr mcp',/)
  assert.doesNotMatch(source, /Auto-routing selects the best model for each query/)
  assert.match(source, /flex-col[^']*sm:flex-row/)
  assert.match(source, /whitespace-pre-wrap[^']*wrap-break-word/)
})
