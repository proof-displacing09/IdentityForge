import { defineConfig } from '@playwright/test';
// Browser E2E: requires `npx playwright install chromium` and a running
// stack (docker compose up -d: Keycloak + backend + frontend).
// Base URL from PLAYWRIGHT_BASE_URL, default http://127.0.0.1:5173.
// Specs skip cleanly when the lab is not reachable; a skip is NOT a pass.
//
// Workers (P1-09, v4): the target machine is an 8 GB Windows laptop
// running Keycloak (~1 GB) + the app containers + Chromium at the same
// time, so the default is ONE worker — browser tests run sequentially
// and stay within RAM. This is the config's own cap: sequential
// test CONTAINERS do not by themselves imply a single Chromium worker.
// Override for stronger machines: PLAYWRIGHT_WORKERS=4.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results/playwright-artifacts',
  timeout: 60000,
  retries: 0,
  workers: process.env.PLAYWRIGHT_WORKERS
    ? parseInt(process.env.PLAYWRIGHT_WORKERS, 10)
    : 1,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  // IF-V4-10 (v5): the JSON report is the E2E EVIDENCE, not the exit
  // code — scripts/validate-playwright-report.py parses it and the
  // runners gate on the parsed verdict (counts, the named real-login
  // tests, the one allowed skip, and the target project). The list
  // reporter stays for human-readable console output. The metadata
  // binds the report to the project it was run against: the runners
  // set IDENTITYFORGE_E2E_TARGET to the disposable cold-start
  // project (e.g. identityforge-coldstart-<ts>); unset it means the
  // persistent host lab. The report lands in test-results/ (inside
  // the E2E container that path is mounted to the host test-results/
  // — see docker-compose.test.yml — so it survives `run --rm`).
  // The screenshots run overwrites the same file, so the runners
  // validate the E2E report BEFORE starting the screenshots run.
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/playwright-report.json' }],
  ],
  metadata: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173',
    target: process.env.IDENTITYFORGE_E2E_TARGET ?? 'host-lab',
  },
  webServer: undefined,
});
