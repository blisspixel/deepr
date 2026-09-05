import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import { chromium } from 'playwright'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const output = resolve(frontend, process.env.QA_OUTPUT || 'screenshots/local-ui')
const base = 'http://127.0.0.1:4188'
const expertName = 'Evidence 100% Laboratory'
const expert = {
  name: expertName, description: 'Synthetic fixture for local interface validation.',
  domain: 'Evidence inspection', document_count: 3, finding_count: 2, studied_findings: 2,
  gap_count: 1, total_cost: 0, created_at: '2026-09-01T10:00:00Z',
  last_active: '2026-09-05T10:00:00Z', roster_tier: 'flagship', roster_ready: true,
  standpoint: 'Prefer retained, dated evidence.', position_count: 1, source_count: 3,
}
const createdExpert = { ...expert, name: 'New Evidence Expert', roster_tier: 'general', roster_ready: false }
const summary = {
  settled: { daily: 0, weekly: 0, monthly: 0, total: 0 },
  exposure: { daily: 0, weekly: 0, monthly: 0 },
  effective_caps: { per_job: 0, daily: 0, weekly: 0, monthly: 0 },
  remaining: { daily: 0, weekly: 0, monthly: 0 }, calendar_cap_periods: ['monthly'],
  active_holds: 0, unresolved_holds: 0, unresolved_exposure: 0,
  authority_mode: 'spend_wallet', spend_wallet_spent: 0, spend_wallet_reserved: 0,
  spend_wallet_authorized: 0, spend_wallet_available: 0, spend_wallet_protection: 'local_only',
  effective_monthly_limit: 0, monthly_limit: 0, monthly: 0, total: 0, daily: 0, weekly: 0,
  paid_api_frozen: true, freeze_reason: 'Synthetic fixture with no paid authority.',
  over_budget: false, avg_cost_per_job: 0, completed_jobs: 0, total_jobs: 0,
}
const results = []
const errors = []
const requests = []
const server = await createServer({
  configFile: false, root: frontend, plugins: [react()],
  cacheDir: resolve(frontend, 'node_modules/.vite-ui-validation'),
  resolve: { alias: { '@': resolve(frontend, 'src') } },
  server: { host: '127.0.0.1', port: 4188, strictPort: true, proxy: {} },
  logLevel: 'error',
})
await mkdir(output, { recursive: true })
await server.listen()
let browser

async function fixture(width, theme) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme })
  const state = { mode: 'populated', unknownMoney: false, funded: false, created: false }
  await context.routeWebSocket('**/*', (socket) => socket.close({ code: 1000, reason: 'Isolated interface fixture' }))
  await context.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.origin !== base) return route.abort()
    if (url.pathname.startsWith('/socket.io')) return route.fulfill({ status: 503, body: 'Offline fixture' })
    if (!url.pathname.startsWith('/api/')) return route.continue()
    requests.push({ method: request.method(), path: url.pathname })
    const json = (payload, status = 200) => route.fulfill({ status, json: payload })
    if (request.method() !== 'GET') {
      if (request.method() === 'POST' && url.pathname === '/api/experts') {
        assert.equal(request.postDataJSON().name, createdExpert.name)
        state.created = true
        return json({ expert: createdExpert }, 201)
      }
      if (url.pathname === '/api/cost/estimate') {
        return json({ allowed: true, estimate: { min_cost: 0.01, max_cost: 0.03, expected_cost: 0.02 } })
      }
      errors.push(`Unexpected mutation: ${request.method()} ${url.pathname}`)
      return json({ error: 'Fixture refuses mutations' }, 405)
    }
    if (url.pathname === '/api/cost/limits') return json({ limits: { per_job: 0, daily: 0, monthly: 0, expert_chat_max: 0, mutable_fields: [] } })
    if (url.pathname === '/api/cost/summary') {
      if (state.unknownMoney) return json({ error: 'Synthetic accounting failure' }, 500)
      return json({ summary: state.funded ? { ...summary, paid_api_frozen: false, spend_wallet_authorized: 5, effective_monthly_limit: 5 } : summary })
    }
    if (url.pathname === '/api/cost/trends') return json({ trends: { daily: [], cumulative: 0 } })
    if (url.pathname === '/api/cost/integrity') return json({ integrity: { days: 45, matched_spend: 0, orphaned_spend: 0, matched_events: 0, orphaned_events: 0 } })
    if (url.pathname === '/api/cost/breakdown') return json({ breakdown: [] })
    if (url.pathname === '/api/jobs/stats') return json({ stats: { queued: 0, processing: 0, completed: 0, failed: 0, total: 0 } })
    if (url.pathname === '/api/jobs') return state.mode === 'error' ? json({ error: 'Synthetic activity failure' }, 500) : json({ jobs: [], total: 0 })
    if (url.pathname === '/api/experts') return state.mode === 'error' ? json({ error: 'Synthetic expert failure' }, 500) : json({ experts: state.mode === 'empty' ? [] : state.created ? [expert, createdExpert] : [expert] })
    if (url.pathname.endsWith('/claims')) return state.mode === 'claims-error' ? json({ error: 'Synthetic claim failure' }, 500) : json({ claims: state.mode === 'claims-empty' ? [] : [{ id: 'claim-1', statement: 'This is a retained synthetic claim.', confidence: 0.8, domain: 'Evidence inspection', sources: [{ id: 'source-1' }] }] })
    if (url.pathname.endsWith('/conversations')) return json({ conversations: [{ session_id: 'saved-1', preview: 'A retained conversation', message_count: 1, cost: 0 }] })
    if (url.pathname.endsWith('/conversations/saved-1')) return json({ session_id: 'saved-1', messages: [{ role: 'assistant', content: 'Retained conversation evidence.' }] })
    if (url.pathname.endsWith('/gaps')) return json({ gaps: [] })
    if (url.pathname.startsWith('/api/experts/')) return state.mode === 'error' ? json({ error: 'Synthetic profile failure' }, 500) : json({ expert })
    if (url.pathname === '/api/results') {
      if (state.mode === 'error') return json({ error: 'Synthetic results failure' }, 500)
      const reports = state.mode === 'populated' && !url.searchParams.get('search')
        ? [{ id: 'fixture-report', prompt: 'A synthetic retained report', content: 'A saved report used only for interface validation.', model: 'local-fixture', cost: 0, citations_count: 1, completed_at: '2026-09-05T10:00:00Z' }]
        : []
      return json({ results: reports, total: reports.length })
    }
    if (url.pathname === '/api/config') return json({ config: { has_api_key: state.funded, default_model: 'o4-mini-deep-research', monthly_limit: 5 } })
    if (url.pathname === '/api/health') return json({ healthy: true, version: 'synthetic-fixture' })
    errors.push(`Unexpected read: ${url.pathname}`)
    return json({ error: 'No fixture defined' }, 404)
  })
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(error.message))
  const checkLayout = async (label) => {
    await page.locator('footer[aria-label="Workspace status"]').waitFor()
    await page.evaluate(() => document.fonts.ready)
    const metrics = await page.evaluate(() => {
      const footer = document.querySelector('footer[aria-label="Workspace status"]')
      const main = document.querySelector('main')
      return { viewport: innerWidth, document: document.documentElement.scrollWidth, main: main.scrollWidth, mainWidth: main.clientWidth, footer: footer.scrollWidth, footerWidth: footer.clientWidth }
    })
    assert.ok(metrics.document <= width + 1, `${label}: document overflow ${JSON.stringify(metrics)}`)
    assert.ok(metrics.main <= metrics.mainWidth + 1, `${label}: main overflow ${JSON.stringify(metrics)}`)
    assert.ok(metrics.footer <= metrics.footerWidth + 1, `${label}: footer overflow ${JSON.stringify(metrics)}`)
    assert.ok(await page.getByRole('link', { name: /^Open cost accounting/ }).isVisible())
    results.push({ label, width, theme, metrics })
  }
  await page.goto(`${base}/experts`)
  const card = page.getByRole('link', { name: new RegExp(expertName) })
  await card.waitFor()
  await checkLayout('populated-experts')
  await card.focus()
  assert.ok(await card.evaluate((element) => element.matches(':focus-visible')))
  assert.notEqual(await card.evaluate((element) => getComputedStyle(element).boxShadow), 'none')
  await page.keyboard.press('Enter')
  await page.getByText('This is a retained synthetic claim.').waitFor()
  assert.equal(await page.getByRole('button', { name: 'Claims', exact: true }).getAttribute('aria-pressed'), 'true')
  assert.equal(await page.getByRole('button', { name: 'Chat (unavailable)', exact: true }).getAttribute('aria-pressed'), 'false')
  await page.getByText('Consult locally with the CLI', { exact: true }).click()
  assert.match(await page.locator('details code').innerText(), /--expert='Evidence 100% Laboratory' --local/)
  await checkLayout('claims-and-local-handoff')
  await page.screenshot({ path: resolve(output, `synthetic-profile-${theme}-${width}.png`), animations: 'disabled' })
  await page.getByRole('button', { name: 'Chat (unavailable)', exact: true }).click()
  await page.getByText('Browser chat is unavailable in this release.').waitFor()
  assert.ok(await page.getByRole('button', { name: 'Send message', exact: true }).isDisabled())
  if (width < 768) await page.getByRole('combobox', { name: 'Saved conversation' }).selectOption('saved-1')
  else await page.getByRole('button', { name: 'A retained conversation', exact: true }).click()
  await page.getByText('Retained conversation evidence.').waitFor()
  await checkLayout('saved-chat')
  await page.goBack()
  assert.equal(await page.getByRole('button', { name: 'Claims', exact: true }).getAttribute('aria-pressed'), 'true')
  state.mode = 'claims-error'
  await page.goto(`${base}/experts/${encodeURIComponent(expertName)}`)
  await page.getByText('Claims unavailable', { exact: true }).waitFor()
  assert.equal(await page.getByText('No claims yet', { exact: true }).count(), 0)
  state.mode = 'claims-empty'
  await page.reload()
  await page.getByText('No claims yet', { exact: true }).waitFor()
  state.mode = 'populated'
  await page.goto(`${base}/experts`)
  await page.getByRole('textbox').fill('unmatched synthetic filter')
  await page.getByText('No matches', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Show all experts' }).click()
  await card.waitFor()
  if (width < 768) await page.getByRole('button', { name: 'Open navigation menu' }).click()
  assert.equal(await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Experts', exact: true }).getAttribute('aria-current'), 'page')
  if (width < 768) await page.keyboard.press('Escape')
  await page.getByRole('combobox', { name: 'Roster view' }).click()
  await page.getByRole('option', { name: 'Flagship roster', exact: true }).click()
  await page.getByRole('textbox', { name: 'Search experts' }).fill(expertName)
  await page.getByRole('button', { name: 'Create Expert', exact: true }).click()
  await page.getByRole('textbox', { name: 'Name *', exact: true }).fill(createdExpert.name)
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.getByRole('link', { name: new RegExp(createdExpert.name) }).waitFor()
  assert.equal(await page.getByRole('textbox', { name: 'Search experts' }).inputValue(), '')
  await checkLayout('created-expert-visible')
  await page.goto(`${base}/results`)
  await page.getByRole('link', { name: /A synthetic retained report/ }).waitFor()
  await checkLayout('populated-results')
  state.mode = 'empty'
  await page.goto(`${base}/experts`)
  await page.getByText('No experts yet', { exact: true }).waitFor()
  await page.goto(`${base}/results`)
  await page.getByText('No saved reports yet', { exact: true }).waitFor()
  await page.getByRole('textbox', { name: 'Search research results' }).fill('unmatched')
  await page.getByText('No matching results', { exact: true }).waitFor()
  assert.ok(await page.getByRole('textbox', { name: 'Search research results' }).evaluate((element) => element === document.activeElement), 'Searching must preserve keyboard focus when the query loads')
  await page.getByRole('button', { name: 'Clear search' }).click()
  await page.getByText('No saved reports yet', { exact: true }).waitFor()
  await page.goto(base)
  await page.getByText('Start with a local expert', { exact: true }).waitFor()
  await checkLayout('empty-overview')
  await page.screenshot({ path: resolve(output, `synthetic-overview-${theme}-${width}.png`), animations: 'disabled' })
  await page.getByRole('link', { name: /^Open cost accounting/ }).click()
  await page.getByRole('heading', { name: 'Cost Intelligence', exact: true }).waitFor()
  assert.equal(new URL(page.url()).pathname, '/costs')
  state.mode = 'error'
  for (const [path, text] of [['/experts', 'Unable to load experts'], ['/results', 'Unable to load results'], ['/', 'Activity is unavailable']]) {
    await page.goto(`${base}${path}`)
    await page.getByText(text, { exact: true }).waitFor()
    assert.equal(await page.getByText('Start with a local expert', { exact: true }).count(), 0)
    await checkLayout(`error-${path}`)
  }
  state.mode = 'empty'
  state.unknownMoney = true
  await page.goto(`${base}/experts`)
  await page.getByRole('link', { name: /^Open cost accounting.*UNKNOWN/ }).waitFor()
  await checkLayout('unknown-accounting')
  assert.match(await page.getByRole('link', { name: /^Open cost accounting/ }).getAttribute('aria-label'), /UNKNOWN \/ UNKNOWN/)
  state.unknownMoney = false
  state.funded = true
  await page.goto(`${base}/research`)
  await page.getByText('Research preview', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Submit', exact: true }).waitFor()
  await page.getByRole('textbox').first().fill('A synthetic request that must remain a preview even with funded accounting.')
  await page.getByRole('checkbox', { name: /Approve metered OpenAI API use/ }).check()
  assert.ok(await page.getByRole('button', { name: 'Submit', exact: true }).isDisabled())
  await checkLayout('research-preview-funded')
  await context.close()
}

try {
  browser = await chromium.launch({ headless: true })
  for (const theme of ['light', 'dark']) {
    for (const width of [320, 390, 1440]) {
      await fixture(width, theme)
      console.log(`Validated ${theme} at ${width}px`)
    }
  }
  assert.deepEqual(errors, [])
  await writeFile(resolve(output, 'validation.json'), JSON.stringify({ results, requests, errors }, null, 2))
  console.log(`Passed ${results.length} layout/state checks. No backend or provider was contacted.`)
} finally {
  await browser?.close()
  await server.close()
}
