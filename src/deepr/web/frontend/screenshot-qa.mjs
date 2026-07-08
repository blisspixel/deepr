import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Port + appearance are configurable so the QA loop can run against whatever
// port vite picked and capture both themes / a chosen accent.
//   QA_BASE=http://localhost:3002 QA_API=http://localhost:5002 QA_THEME=dark QA_ACCENT=indigo node screenshot-qa.mjs
const BASE = process.env.QA_BASE || 'http://localhost:3000';
const API = process.env.QA_API || 'http://localhost:5000';
const THEME = process.env.QA_THEME || 'light';
const ACCENT = process.env.QA_ACCENT || 'teal';
const DEMO = ['1', 'true', 'yes', 'on'].includes((process.env.QA_DEMO || '').trim().toLowerCase());
const ALLOW_OVER_LIMIT_COST_SCREENSHOT = ['1', 'true', 'yes', 'on'].includes(
  (process.env.QA_ALLOW_OVER_LIMIT_COST_SCREENSHOT || '').trim().toLowerCase()
);
const apiUrl = (path) => `${API.replace(/\/+$/, '')}${path}`;

const screenshotDir = join(__dirname, 'screenshots', THEME === 'dark' ? 'dark' : 'light');
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
    const rich = experts.find(e => (e.total_documents || e.documents || 0) >= 5) || experts[0];
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
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });

  // Seed the persisted UI store so theme + accent apply before first paint,
  // exactly as a real user's localStorage would (matches the FOUC script).
  await context.addInitScript(([theme, accent]) => {
    localStorage.setItem(
      'deepr-ui-store',
      JSON.stringify({ state: { theme, accent, sidebarCollapsed: false }, version: 0 })
    );
  }, [THEME, ACCENT]);

  for (const pg of pages) {
    const page = await context.newPage();
    const url = `${BASE}${pg.path}`;
    console.log(`Navigating to ${pg.name}: ${url}`);

    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (err) {
      console.error(`  Warning: navigation timeout for ${pg.name}, continuing with screenshot wait`);
    }

    try {
      await page.waitForLoadState('networkidle', { timeout: 10000 });
    } catch {
      console.error(`  Warning: network idle timeout for ${pg.name}, continuing after fixed wait`);
    }

    // Extra wait for React Query, lazy-loaded charts, and route-level data.
    await page.waitForTimeout(2500);
    if (pg.afterLoad) {
      await pg.afterLoad(page);
    }

    const filepath = join(screenshotDir, `${pg.name}.png`);
    await page.screenshot({ path: filepath, fullPage: FULL_PAGE });
    console.log(`  Saved: ${filepath}`);
    await page.close();
  }

  await browser.close();
  console.log('\nDone! All screenshots saved to:', screenshotDir);
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
