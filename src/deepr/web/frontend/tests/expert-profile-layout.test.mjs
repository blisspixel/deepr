import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const profileSource = readFileSync(new URL('../src/pages/expert-profile.tsx', import.meta.url), 'utf8')

test('claim columns remain readable for long expert domains', () => {
  assert.match(profileSource, /min-w-\[900px\] table-fixed/)
  assert.match(profileSource, /w-\[52%\][\s\S]*w-\[28%\]/)
  assert.match(profileSource, /title=\{claim\.domain\}/)
  assert.match(profileSource, /line-clamp-3 break-words/)
})
