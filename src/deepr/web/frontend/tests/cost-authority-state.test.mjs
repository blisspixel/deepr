import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const costs = readFileSync(new URL('../src/pages/cost-intelligence.tsx', import.meta.url), 'utf8')
const overview = readFileSync(new URL('../src/pages/overview.tsx', import.meta.url), 'utf8')
const statusBar = readFileSync(new URL('../src/components/layout/status-bar.tsx', import.meta.url), 'utf8')
const settings = readFileSync(new URL('../src/pages/settings.tsx', import.meta.url), 'utf8')

test('cost surfaces render active exposure and an explicit paid API freeze', () => {
  assert.match(costs, /moneyLabel\(summary\?\.exposure\.monthly\)/)
  assert.match(costs, /moneyLabel\(summary\?\.active_holds\)/)
  assert.match(costs, /Paid API dispatch is frozen/)
  assert.match(overview, /moneyLabel\(costSummary\?\.exposure\.monthly\)/)
  assert.match(statusBar, /PAID API FROZEN/)
  assert.match(statusBar, /attendedGrant \? 'API grant' : 'Month exposure'/)
  assert.match(overview, /Attended API grant:/)
  assert.match(costs, /Attended API grant is active/)
})

test('unknown canonical money state is blocked and never rendered as zero', () => {
  for (const source of [costs, overview, statusBar]) {
    assert.match(source, /UNKNOWN/)
    assert.doesNotMatch(source, /exposure\.(daily|monthly) \?\? 0/)
    assert.doesNotMatch(source, /active_holds \?\? 0/)
    assert.doesNotMatch(source, /settled\.total \?\? 0/)
  }
  assert.match(costs, /paid API dispatch must remain blocked/i)
  assert.match(overview, /paid API dispatch must remain blocked/i)
  assert.match(statusBar, /PAID API BLOCKED/)
  assert.match(statusBar, /UNKNOWN \/ UNKNOWN/)
})

test('zero cost limits are preserved instead of replaced with display defaults', () => {
  for (const source of [costs, overview, statusBar, settings]) {
    assert.doesNotMatch(source, /(daily_limit|monthly_limit|effective_monthly_limit)[^\n]*\|\|/)
  }
  assert.match(statusBar, /'Month exposure'/)
  assert.match(statusBar, /formatCurrency\(costSummary\.effective_monthly_limit\)/)
  assert.match(costs, /OVER \$0 CEILING/)
  assert.match(overview, /OVER \$0 CEILING/)
})

test('dashboard mutates only the canonical monthly authority', () => {
  assert.match(costs, /updateLimitsMutation\.mutate\(\{ monthly:/)
  assert.doesNotMatch(costs, /handleSliderChange\('per_job'/)
  assert.doesNotMatch(settings, /updates\.daily_limit\s*=/)
  assert.match(settings, /updates\.monthly_limit = monthly/)
})
