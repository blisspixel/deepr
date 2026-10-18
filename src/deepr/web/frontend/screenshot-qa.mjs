import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';
import { join, dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Port + appearance are configurable so the QA loop can run against whatever
// port vite picked and capture both themes / a chosen accent and expert.
//   QA_BASE=http://localhost:3002 QA_API=http://localhost:5002 QA_THEME=dark QA_ACCENT=indigo QA_EXPERT="Temporal Knowledge Graphs" node screenshot-qa.mjs
const BASE = process.env.QA_BASE || 'http://localhost:3000';
const API = process.env.QA_API || 'http://localhost:5000';
const THEME = process.env.QA_THEME || 'light';
const ACCENT = process.env.QA_ACCENT || 'teal';
const PREFERRED_EXPERT = (process.env.QA_EXPERT || '').trim();
const DEMO = ['1', 'true', 'yes', 'on'].includes((process.env.QA_DEMO || '').trim().toLowerCase());
const ALLOW_OVER_LIMIT_COST_SCREENSHOT = ['1', 'true', 'yes', 'on'].includes(
  (process.env.QA_ALLOW_OVER_LIMIT_COST_SCREENSHOT || '').trim().toLowerCase()
);
const CONTENT_ONLY = process.argv.includes('--content');
const VIEWPORT = { width: 1440, height: 900 };
const STATUS_BAR_HEIGHT = 32;
const apiUrl = (path) => `${API.replace(/\/+$/, '')}${path}`;

assert.ok(['light', 'dark'].includes(THEME), 'QA_THEME must be light or dark');
const screenshotDir = join(resolve(process.env.QA_OUTPUT || join(__dirname, 'screenshots')), THEME);
const allowedOrigins = new Set([new URL(BASE).origin, new URL(API).origin]);
mkdirSync(screenshotDir, { recursive: true });

async function fetchJson(path, options = {}) {
  const response = await fetch(apiUrl(path), options);
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`${path} returned ${response.status}: ${text.slice(0, 200)}`);
  }
  return response.json();
}

async function seedDemoData() {
  if (!DEMO) return;
  await fetchJson('/api/demo/load', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm: 'DELETE_ALL_DATA' }),
  });
  console.log('Seeded backend demo data via /api/demo/load');
}

async function assertCostScreenshotIsSafe() {
  if (ALLOW_OVER_LIMIT_COST_SCREENSHOT) return;

  const data = await fetchJson('/api/cost/summary');
  const summary = data.summary || {};
  const daily = Number(summary.daily || 0);
  const monthly = Number(summary.monthly || 0);
  const dailyLimit = Number(summary.daily_limit || 0);
  const monthlyLimit = Number(summary.monthly_limit || 0);
  const dailyUtilization = dailyLimit > 0 ? (daily / dailyLimit) * 100 : 0;
  const monthlyUtilization = monthlyLimit > 0 ? (monthly / monthlyLimit) * 100 : 0;

  if (dailyUtilization > 80 || monthlyUtilization > 80 || daily > dailyLimit || monthly > monthlyLimit) {
    throw new Error(
      [
        'Refusing to capture screenshots from over-limit cost data.',
        `daily=$${daily.toFixed(2)} / $${dailyLimit.toFixed(2)} (${dailyUtilization.toFixed(0)}%)`,
        `monthly=$${monthly.toFixed(2)} / $${monthlyLimit.toFixed(2)} (${monthlyUtilization.toFixed(0)}%).`,
        'Use an isolated DEEPR_COST_DATA_DIR for screenshot demo data, or set QA_ALLOW_OVER_LIMIT_COST_SCREENSHOT=1 deliberately.',
      ].join(' ')
    );
  }
}

async function getCaptureContext() {
  const configData = await fetchJson('/api/jobs?limit=20');
  const jobs = configData.jobs || [];
  const jobId = (jobs.find(j => (j.status || '').toLowerCase() === 'completed') || jobs[0])?.id || 'missing';

  let expertName = 'Behavioral Economics';
  try {
    const expertsData = await fetchJson('/api/experts');
    const experts = expertsData.experts || expertsData || [];
    const preferred = experts.find(e => e.name === PREFERRED_EXPERT);
    const richnessScore = (expert) =>
      (expert.roster_tier === 'flagship' ? 1000 : 0) +
      (expert.position_count || 0) * 100 +
      (expert.grounded_findings || 0) * 10 +
      (expert.source_count || 0);
    const rich =
      preferred ||
      [...experts].sort((left, right) => richnessScore(right) - richnessScore(left))[0];
    if (rich?.name) expertName = rich.name;
  } catch {
    // fall back to default
  }

  console.log(`Using job ID: ${jobId}, expert: ${expertName}`);
  return { jobId, expertName };
}

// fullPage QA captures by default; pass --viewport for README-style crops
const FULL_PAGE = !process.argv.includes('--viewport');

function buildPages(jobId, expertName) {
  return [
    { name: '01-overview',        path: '/' },
    { name: '02-research-studio', path: '/research' },
    { name: '03-research-live',   path: `/research/${jobId}` },
    { name: '04-results-library', path: '/results' },
    { name: '05-result-detail',   path: `/results/${jobId}` },
    { name: '06-expert-hub',      path: '/experts' },
    { name: '07-expert-profile',  path: `/experts/${encodeURIComponent(expertName)}?tab=claims` },
    { name: '08-cost-intelligence', path: '/costs' },
    { name: '09-trace-explorer',  path: `/traces/${jobId}` },
    {
      name: '10-benchmarks',
      path: '/models',
      afterLoad: async (page) => {
        const chatButtons = page.getByRole('button', { name: /Chat/ });
        if (await chatButtons.count()) {
          await chatButtons.first().click();
          await page.waitForTimeout(500);
        }
      },
    },
    { name: '11-settings',        path: '/settings' },
    { name: '12-help',            path: '/help' },
  ];
}

async function main() {
  await seedDemoData();
  await assertCostScreenshotIsSafe();
  const { jobId, expertName } = await getCaptureContext();
  const pages = buildPages(jobId, expertName);

  const browser = await chromium.launch({ headless: true });
  const observations = { consoleErrors: [], pageErrors: [], failedResponses: [], externalRequests: [] };
  const captures = [];
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    colorScheme: THEME,
    storageState: { cookies: [], origins: [{
      origin: new URL(BASE).origin,
      localStorage: [{ name: 'deepr-ui-store', value: JSON.stringify({
        state: { theme: THEME, accent: ACCENT, sidebarCollapsed: false }, version: 0,
      }) }],
    }] },
  });
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!allowedOrigins.has(url.origin)) {
      observations.externalRequests.push(url.href.slice(0, 200));
      return route.abort();
    }
    return route.continue();
  });
  context.on('page', (page) => {
    page.on('console', (message) => {
      if (message.type() === 'error') observations.consoleErrors.push(message.text().slice(0, 500));
    });
    page.on('pageerror', (error) => observations.pageErrors.push(String(error).slice(0, 500)));
    page.on('response', (response) => {
      if (response.status() >= 400) observations.failedResponses.push({ url: response.url(), status: response.status() });
    });
  });
  try {
    for (const pg of pages) {
      const page = await context.newPage();
      const url = `${BASE}${pg.path}`;
      console.log(`Navigating to ${pg.name}: ${url}`);

      // Hold the application modules, preserving production bytes. The blocking
      // theme initializer must apply the stored preference before React can run.
      let releaseModules;
      const gate = new Promise((resolve) => { releaseModules = resolve; });
      let observedModule;
      let moduleTimeout;
      const moduleRequested = new Promise((resolve, reject) => {
        observedModule = () => { clearTimeout(moduleTimeout); resolve(); };
        moduleTimeout = setTimeout(() => reject(new Error('No application module was observed')), 10000);
      });
      await page.route((requestUrl) => requestUrl.origin === new URL(BASE).origin &&
        ((requestUrl.pathname.startsWith('/assets/') && requestUrl.pathname.endsWith('.js')) || requestUrl.pathname === '/src/main.tsx'), async (route) => {
        observedModule();
        await gate;
        await route.continue();
      });
      let firstPaint;
      try {
        const response = await page.goto(url, { waitUntil: 'commit', timeout: 30000 });
        assert.ok(response?.ok(), `${pg.name}: document navigation failed`);
        await Promise.all([
          page.waitForFunction((theme) => document.documentElement.classList.contains(theme), THEME, { timeout: 10000 }),
          moduleRequested,
          page.waitForFunction(() => Boolean(getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()), undefined, { timeout: 10000 }),
        ]);
        firstPaint = await page.evaluate(() => ({
          classes: document.documentElement.className,
          primary: getComputedStyle(document.documentElement).getPropertyValue('--primary').trim(),
          applicationMounted: Boolean(document.getElementById('root')?.childElementCount),
        }));
        assert.equal(firstPaint.applicationMounted, false, `${pg.name}: theme was checked after application startup`);
      } finally {
        clearTimeout(moduleTimeout);
        releaseModules();
      }
      await page.waitForLoadState('networkidle', { timeout: 15000 });
      await page.locator('main').waitFor({ state: 'visible' });
      await page.evaluate(() => document.fonts.ready);
      assert.equal(await page.evaluate((theme) => document.documentElement.classList.contains(theme), THEME), true);
      assert.ok((await page.locator('main').innerText()).trim(), `${pg.name}: empty route content`);

      // Extra wait for React Query, lazy-loaded charts, and route-level data.
      await page.waitForTimeout(2500);
      if (pg.afterLoad) {
        await pg.afterLoad(page);
      }

      const filepath = join(screenshotDir, `${pg.name}.png`);
      const capture = CONTENT_ONLY
        ? { path: filepath, clip: { x: 0, y: 0, width: VIEWPORT.width, height: VIEWPORT.height - STATUS_BAR_HEIGHT } }
        : { path: filepath, fullPage: FULL_PAGE };
      await page.screenshot({ ...capture, animations: 'disabled' });
      captures.push({ name: pg.name, path: pg.path, firstPaint, theme: THEME });
      console.log(`  Saved: ${filepath}`);
      await page.close();
    }

    assert.equal(captures.length, pages.length);
    assert.deepEqual(observations, { consoleErrors: [], pageErrors: [], failedResponses: [], externalRequests: [] });
  } finally {
    writeFileSync(join(screenshotDir, 'receipt.json'), JSON.stringify({ theme: THEME, captures, observations }, null, 2));
    await browser.close();
  }
  console.log('\nDone! All screenshots saved to:', screenshotDir);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
