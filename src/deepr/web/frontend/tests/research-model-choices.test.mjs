import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const retired = [
  'gpt-5.6-sol',
  'gpt-5.6-terra',
  'o3-deep-research',
  'o4-mini-deep-research',
]

const current = ['gpt-6.1-sol', 'gpt-6.1-terra', 'gpt-6-luna', 'gpt-6-astra']

const files = [
  ['constants', '../src/lib/constants.ts'],
  ['studio', '../src/pages/research-studio.tsx'],
  ['settings', '../src/pages/settings.tsx'],
  ['help', '../src/pages/help.tsx'],
]

test('dashboard new-request choices use the current research models', async () => {
  const sources = Object.fromEntries(await Promise.all(files.map(async ([name, file]) => {
    return [name, await readFile(new URL(file, import.meta.url), 'utf8')]
  })))

  for (const id of current) {
    assert.match(sources.constants, new RegExp(`value: '${id}'`))
  }
  assert.match(sources.constants, /DEFAULT_RESEARCH_MODEL = 'gpt-6\.1-sol'/)
  assert.match(sources.studio, /const DEFAULT_MODEL = DEFAULT_RESEARCH_MODEL/)
  assert.match(sources.settings, /MODELS\.map\(\(model\)/)
  assert.match(sources.settings, /default_model: DEFAULT_RESEARCH_MODEL/)
  assert.match(sources.help, /grok-4\.7/)
  assert.match(sources.help, /claude-opus-5-5/)
  assert.match(sources.help, /gemini-4-carbon/)
  assert.doesNotMatch(sources.studio, /o4-mini is faster/)
  assert.doesNotMatch(sources.studio, /o3 is deeper/)

  for (const [name, source] of Object.entries(sources)) {
    for (const id of retired) {
      assert.equal(source.includes(id), false, `${name} still advertises ${id}`)
    }
  }
})
