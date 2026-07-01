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
const apiUrl = (path) => `${API.replace(/\/+$/, '')}${path}`;

const screenshotDir = join(__dirname, 'screenshots', THEME === 'dark' ? 'dark' : 'light');
mkdirSync(screenshotDir, { recursive: true });

// Fetch a valid job ID from the running backend
const configResp = await fetch(apiUrl('/api/jobs?limit=20'));
const configData = await configResp.json();
// Prefer a completed job so detail/trace pages have content
const jobs = configData.jobs || [];
const JOB_ID = (jobs.find(j => (j.status || '').toLowerCase() === 'completed') || jobs[0])?.id || 'missing';

// Pick an expert dynamically - prefer one with documents (rich profile page)
let EXPERT_NAME = 'Behavioral Economics';
try {
  const expertsResp = await fetch(apiUrl('/api/experts'));
  const expertsData = await expertsResp.json();
  const experts = expertsData.experts || expertsData || [];
  const rich = experts.find(e => (e.total_documents || e.documents || 0) >= 5) || experts[0];
  if (rich?.name) EXPERT_NAME = rich.name;
} catch { /* fall back to default */ }
console.log(`Using job ID: ${JOB_ID}, expert: ${EXPERT_NAME}`);

// fullPage QA captures by default; pass --viewport for README-style crops
const FULL_PAGE = !process.argv.includes('--viewport');

const pages = [
  { name: '01-overview',        path: '/' },
  { name: '02-research-studio', path: '/research' },
  { name: '03-research-live',   path: `/research/${JOB_ID}` },
  { name: '04-results-library', path: '/results' },
  { name: '05-result-detail',   path: `/results/${JOB_ID}` },
  { name: '06-expert-hub',      path: '/experts' },
  { name: '07-expert-profile',  path: `/experts/${encodeURIComponent(EXPERT_NAME)}?tab=claims` },
  { name: '08-cost-intelligence', path: '/costs' },
  { name: '09-trace-explorer',  path: `/traces/${JOB_ID}` },
  {
    name: '10-benchmarks',
    path: '/models',
    afterLoad: async (page) => {
      await page.getByRole('button', { name: /^Chat \(/ }).click();
      await page.waitForTimeout(500);
    },
  },
  { name: '11-settings',        path: '/settings' },
  { name: '12-help',            path: '/help' },
];

async function main() {
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
      await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
      // Extra wait for lazy-loaded content and charts
      await page.waitForTimeout(2000);
      if (pg.afterLoad) {
        await pg.afterLoad(page);
      }
    } catch (err) {
      console.error(`  Warning: timeout for ${pg.name}, taking screenshot anyway`);
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
