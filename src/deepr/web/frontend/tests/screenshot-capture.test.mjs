import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const screenshotSource = readFileSync(new URL('../screenshot-qa.mjs', import.meta.url), 'utf8')

test('screenshot expert selection follows the current fleet summary contract', () => {
  assert.match(screenshotSource, /process\.env\.QA_EXPERT/)
  assert.match(screenshotSource, /expert\.position_count/)
  assert.match(screenshotSource, /expert\.grounded_findings/)
  assert.match(screenshotSource, /expert\.source_count/)
  assert.doesNotMatch(screenshotSource, /expert\.total_documents \|\| expert\.documents/)
})

test('README framing can omit only the fixed status bar', () => {
  assert.match(screenshotSource, /process\.argv\.includes\('--content'\)/)
  assert.match(screenshotSource, /VIEWPORT\.height - STATUS_BAR_HEIGHT/)
})
