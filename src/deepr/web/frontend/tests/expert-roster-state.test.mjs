import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const hub = readFileSync(new URL('../src/pages/expert-hub.tsx', import.meta.url), 'utf8')

test('expert hub defaults to the explicit flagship tier without hiding the full roster', () => {
  assert.match(hub, /flagshipCount > 0 \? 'flagship' : 'all'/)
  assert.match(hub, /experts\.filter\(e => e\.roster_tier === 'flagship'\)/)
  assert.match(hub, /<SelectItem value="flagship">Flagship roster<\/SelectItem>/)
  assert.match(hub, /<SelectItem value="all">All experts<\/SelectItem>/)
})

test('expert cards expose durable presentation structure', () => {
  assert.match(hub, /flagshipReadyCount/)
  assert.match(hub, /of \$\{flagshipCount\} flagship ready/)
  assert.match(hub, /allReadyCount/)
  assert.match(hub, /expert\.position_count/)
  assert.match(hub, /expert\.studied_findings/)
  assert.match(hub, /expert\.source_count/)
  assert.match(hub, /!expert\.standpoint/)
  assert.match(hub, /portraitUrl=\{expert\.portrait_url\}/)
})
