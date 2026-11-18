import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

/**
 * Responsive screenshots — Trustline Atelier v3 (real browser, live stack).
 *
 * Captures all 12 views at EIGHT widths (320, 360, 390, 768, 1024, 1280, 1440, 1920)
 * into e2e/screenshots/, plus logged-out / signed-in / access-denied /
 * empty / loading / error / confirmation states and zoom equivalents.
 * Every view at every width carries a PROGRAMMATIC overflow assertion
 * (document scrollWidth <= viewport innerWidth) — a passing run means
 * no unintended horizontal overflow was measured, not just that files
 * were written. The PNGs are then inspected by eye for clipping,
 * overlap, contrast and alignment (see docs/UI_DESIGN_SYSTEM.md).
 *
 * Skips cleanly when the lab is not reachable. The reset modal is
 * captured in a separate officer-signed-in test (fresh context) and
 * CANCELLED — never confirmed here.
 */

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173';
const API = BASE.replace(':5173', ':8000');
const STUDENT = { username: 'student_01', password: 'LabPass-Student-01!' };
const OFFICER = { username: 'officer_01', password: 'LabPass-Officer-01!' };

const VIEWPORTS = [
  { name: '320x740', width: 320, height: 740 },
  { name: '360x740', width: 360, height: 740 },
  { name: '390x844', width: 390, height: 844 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '1024x768', width: 1024, height: 768 },
  { name: '1280x800', width: 1280, height: 800 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1920x1080', width: 1920, height: 1080 },
] as const;

async function labReady(request: APIRequestContext): Promise<boolean> {
  try {
    const res = await request.get(`${API}/api/v1/lab/status`, { timeout: 5000 });
    if (!res.ok()) return false;
    const body = await res.json();
    return body?.idp?.reachable === true;
  } catch {
    return false;
  }
}

test.beforeAll(async ({ request }) => {
  test.skip(!(await labReady(request)), 'Lab not reachable: Keycloak IdP is not up. Screenshots NOT RUN.');
});

async function signInViaKeycloak(page: Page, user: { username: string; password: string }) {
  await page.goto('/portal');
  await page.getByRole('link', { name: /sign in with local identity provider/i }).click();
  await expect(page.locator('#username')).toBeVisible({ timeout: 15000 });
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#kc-login').click();
  await expect(page).toHaveURL(/\/portal\?login=success/, { timeout: 15000 });
  await expect(page.getByText('Signed-in dashboard')).toBeVisible();
}

async function runScenario(page: Page, id: 'I1' | 'I6') {
  await page.goto('/scenarios');
  await expect(page.getByRole('listbox', { name: 'Scenarios' })).toBeVisible({ timeout: 15000 });
  await page.getByRole('option', { name: new RegExp(`^${id}\\b`) }).click();
  await page.getByRole('button', { name: new RegExp(`^Run ${id}$`) }).click();
  await expect(page.getByText('Session & model state').first()).toBeVisible({ timeout: 30000 });
}

/** Programmatic overflow assertion: no unintended page-level
 *  horizontal overflow at the current viewport. A table that scrolls
 *  inside its own .table-wrap is allowed; the document itself must
 *  not be wider than the viewport. */
async function assertNoOverflow(page: Page, label: string) {
  const m = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(m.scrollWidth, `${label}: document scrollWidth (${m.scrollWidth}) exceeds viewport (${m.innerWidth})`).toBeLessThanOrEqual(m.innerWidth);
}

/** Deterministic settled-data wait (P2-18, v4): a "normal" screenshot
 *  must never capture a loading skeleton. Waits for network quiet,
 *  then for the view's settled marker (or an honest error alert if
 *  the data failed), then asserts no skeleton is still on screen.
 *  If data never settles the wait times out and the test FAILS —
 *  a loading state is never silently screenshotted as measured data. */
async function waitSettled(page: Page, testId?: string) {
  await page.waitForLoadState('networkidle');
  if (testId) {
    await expect(page.getByTestId(testId).or(page.getByRole('alert'))).toBeVisible({ timeout: 15000 });
  }
  await expect(page.locator('.skeleton')).toHaveCount(0, { timeout: 15000 });
}

for (const vp of VIEWPORTS) {
  test(`screenshots @ ${vp.name}`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const shot = async (name: string) => {
      await assertNoOverflow(page, `${vp.name}-${name}`);
      await page.screenshot({ path: `e2e/screenshots/${vp.name}-${name}.png`, fullPage: true });
    };

    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    // P2-18: wait for the measured metric tiles, not just the h1 —
    // the v3 shot captured blank placeholder cards here.
    await waitSettled(page, 'overview-settled');
    await shot('overview');

    // Mobile drawer (narrow viewports only): open it and capture it.
    if (vp.width < 1024) {
      await page.locator('.menu-btn').click();
      await expect(page.getByRole('navigation', { name: 'IdentityForge sections' })).toBeVisible();
      await shot('nav-drawer');
      await page.keyboard.press('Escape');
    }

    await page.goto('/portal');
    await expect(page.getByText('You are not signed in')).toBeVisible();
    await waitSettled(page);
    await shot('portal-signed-out');

    await signInViaKeycloak(page, STUDENT);
    await waitSettled(page);
    await shot('portal-signed-in');

    await runScenario(page, 'I1');
    await shot('scenario-result');

    await runScenario(page, 'I6');
    await page.goto('/flow');
    await expect(page.getByRole('heading', { name: /Flow Inspector/ })).toBeVisible();
    await expect(page.getByText('ID token verified')).toBeVisible();
    await waitSettled(page);
    await shot('atlas-rejected');

    await page.goto('/compare');
    await expect(page.getByRole('heading', { name: 'Secure vs Flawed' })).toBeVisible();
    await waitSettled(page);
    await shot('comparison');

    await page.goto('/findings');
    await expect(page.getByRole('heading', { name: 'Findings & Evidence' })).toBeVisible();
    await waitSettled(page);
    await shot('findings');

    await page.goto('/protocol');
    await expect(page.getByRole('heading', { name: 'Protocol Explorer' })).toBeVisible();
    await waitSettled(page);
    await shot('protocol');

    await page.goto('/rules');
    await expect(page.getByRole('heading', { name: 'Validation Rules' })).toBeVisible();
    await waitSettled(page);
    await shot('rules');

    await page.goto('/boundaries');
    await expect(page.getByRole('heading', { name: 'Identity & Session Boundaries' })).toBeVisible();
    await waitSettled(page);
    await shot('boundaries');

    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Reports & Reviewer Walkthrough' })).toBeVisible();
    await waitSettled(page);
    await shot('reports');

    await page.goto('/learn');
    await expect(page.getByRole('heading', { name: 'Learning Center' })).toBeVisible();
    await waitSettled(page);
    await shot('learn');
  });

  test(`settings + reset modal @ ${vp.name}`, async ({ page }) => {
    // Fresh context: sign in as officer (reset is officer-only).
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await signInViaKeycloak(page, OFFICER);
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Lab Settings' })).toBeVisible();
    // Wait for the operator identity + counts to resolve so the shot
    // shows the populated P0-01 reset card, not the loading state —
    // and for the measured-status card too (v4: the identity check
    // resolves independently of the config/status fetch, so the
    // officer line alone no longer proves the page is settled).
    await expect(page.getByText(/Signed in as officer_01 — reset authorized/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Measured lab status')).toBeVisible({ timeout: 15000 });
    const shot = async (name: string) => {
      await assertNoOverflow(page, `${vp.name}-${name}`);
      await page.screenshot({ path: `e2e/screenshots/${vp.name}-${name}.png`, fullPage: true });
    };
    await shot('settings');

    // Reset modal: open it for the shot, then CANCEL — never confirm
    // here (confirming would wipe backend evidence for other tests).
    await page.getByRole('button', { name: /Reset lab state/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await shot('modal-reset');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
}

test.describe('states, zoom and text size', () => {
  test('findings empty state (fresh browser, no runs)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/findings');
    await expect(page.getByRole('heading', { name: 'Findings & Evidence' })).toBeVisible();
    await assertNoOverflow(page, 'findings-empty');
    await page.screenshot({ path: 'e2e/screenshots/state-findings-empty.png', fullPage: true });
  });

  test('overview loading state (status delayed)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/v1/lab/status', async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      await route.continue();
    });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await assertNoOverflow(page, 'overview-loading');
    await page.screenshot({ path: 'e2e/screenshots/state-overview-loading.png', fullPage: true });
  });

  test('overview error state (status 500)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/v1/lab/status', (route) => route.fulfill({ status: 500, body: 'boom' }));
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByText(/Lab status failed/)).toBeVisible();
    await assertNoOverflow(page, 'overview-error');
    await page.screenshot({ path: 'e2e/screenshots/state-overview-error.png', fullPage: true });
  });

  test('portal access-denied state (student loads officer resource)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signInViaKeycloak(page, STUDENT);
    await page.getByRole('button', { name: /load officer resource/i }).click();
    await expect(page.getByText(/denied/i).first()).toBeVisible();
    await assertNoOverflow(page, 'portal-access-denied');
    await page.screenshot({ path: 'e2e/screenshots/state-portal-access-denied.png', fullPage: true });
  });

  test('overview provider-down state (IdP unreachable, honest not-ready)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/v1/lab/status', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        backend: 'ok',
        issuer: 'http://127.0.0.1:8080/realms/identityforge-lab',
        provider_mode: 'keycloak-local',
        idp: { reachable: false, issuer_matches: null, discovery_url: 'http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration', reason: 'PROVIDER_DOWN — discovery probe failed' },
        last_verified_login: null,
      }),
    }));
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await waitSettled(page, 'overview-settled');
    await expect(page.getByText('Not reachable').first()).toBeVisible();
    await assertNoOverflow(page, 'overview-provider-down');
    await page.screenshot({ path: 'e2e/screenshots/state-overview-provider-down.png', fullPage: true });
  });

  test('overview wrong-issuer state (reachable, issuer mismatch — never Verified)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/v1/lab/status', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        backend: 'ok',
        issuer: 'http://127.0.0.1:8080/realms/identityforge-lab',
        provider_mode: 'keycloak-local',
        idp: { reachable: true, issuer_matches: false, discovery_url: 'http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration', reason: 'ValueError — discovery issuer differs from the configured issuer' },
        last_verified_login: null,
      }),
    }));
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await waitSettled(page, 'overview-settled');
    // IF-V4-05: the tile and the reviewer step must name the mismatch.
    // The step itself must not carry a Verified pill — other steps may
    // legitimately be Verified from earlier real logins the backend
    // still holds, so the assertion is scoped to this step, not the page.
    await expect(page.locator('.metric', { hasText: 'Identity provider' }).getByText('Issuer mismatch')).toBeVisible();
    const step = page.locator('.reviewer-path li', { hasText: 'Start services' });
    await expect(step.getByText('Issuer mismatch')).toBeVisible();
    await expect(step.getByText('Verified', { exact: true })).toHaveCount(0);
    await expect(step.getByText(/does NOT match the configured issuer/)).toBeVisible();
    await assertNoOverflow(page, 'overview-wrong-issuer');
    await page.screenshot({ path: 'e2e/screenshots/state-overview-wrong-issuer.png', fullPage: true });
  });

  test('overview not-run state (no verified login, no live logins)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Override BOTH the live-login list and the status's last verified
    // login: a fresh backend process has no verified login and no live
    // timelines, so the tiles must say NOT RUN / 0 — not reuse a
    // previous test's student_01 session as if it were fresh evidence.
    await page.route('**/api/v1/lab/status', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        backend: 'ok',
        issuer: 'http://127.0.0.1:8080/realms/identityforge-lab',
        provider_mode: 'keycloak-local',
        idp: { reachable: true, issuer_matches: true, discovery_url: 'http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration', reason: 'OK' },
        last_verified_login: null,
      }),
    }));
    await page.route('**/api/v1/live-logins', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ mode: 'LIVE_KEYCLOAK', logins: [] }),
    }));
    // IF-V5-07 (v6): the "Real Keycloak logins observed" tile reads the
    // RETAINED transaction total from /api/v1/lab/counts, not from the
    // live-logins sample above — so a fresh-backend assertion must mock
    // counts to zero too, or a retained transaction from an earlier
    // test's real login leaks into this "no logins" state. (Parent
    // re-run 2026-11-11: without this mock the tile read 1, from the
    // live-gate's retained transaction in the shared dev DB.)
    await page.route('**/api/v1/lab/counts', (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ runs: 0, sessions: 0, sessions_total_issued: 0, live_logins: 0, transactions: 0, events: 0, live_login_transactions: 0, live_login_events: 0, live_login_successful_transactions: 0, live_login_event_limit: 1000, runs_limit: 1000, events_limit: 20000, live_logins_limit: 1000 }),
    }));
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await waitSettled(page, 'overview-settled');
    // The Last verified login tile itself must read NOT RUN, and the
    // live-login count tile must read 0.
    await expect(page.locator('.metric', { hasText: 'Last verified login' }).getByText('NOT RUN', { exact: true })).toBeVisible();
    await expect(page.locator('.metric', { hasText: 'Real Keycloak logins observed' }).getByText('0', { exact: true })).toBeVisible();
    await assertNoOverflow(page, 'overview-not-run');
    await page.screenshot({ path: 'e2e/screenshots/state-overview-not-run.png', fullPage: true });
  });

  test('settings identity-unknown state (/portal/me returns 500)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/v1/portal/me', (route) => route.fulfill({ status: 500, body: 'boom' }));
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Lab Settings' })).toBeVisible();
    await expect(page.getByText(/returned a server error/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: /Retry identity check/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Reset lab state/ })).toBeDisabled();
    await assertNoOverflow(page, 'settings-identity-unknown');
    await page.screenshot({ path: 'e2e/screenshots/state-settings-identity-unknown.png', fullPage: true });
  });

  test('reports stale state (status succeeded, then retry failed — past-tense, never current green)', async ({ page }) => {
    // IF-V7-01: the two-tier step-1 badges under a STALE runtime.
    // Status succeeds once (real passthrough), live logins fail so
    // the Retry button renders, then a retry fails the status fetch
    // and the tier turns STALE: amber past-tense chip, no current
    // green badge, release gate still UNVERIFIED IN THIS BROWSER.
    await page.setViewportSize({ width: 1440, height: 900 });
    let statusCalls = 0;
    await page.route('**/api/v1/lab/status', async (route) => {
      statusCalls += 1;
      // The app shell (topbar) and the Reports page each fetch
      // /lab/status on mount: the first two calls pass through real,
      // later calls (the retry) fail.
      if (statusCalls <= 2) { await route.continue(); return; }
      await route.fulfill({ status: 500, body: 'boom' });
    });
    await page.route('**/api/v1/live-logins', (route) => route.fulfill({ status: 500, body: 'boom' }));
    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Reports & Reviewer Walkthrough' })).toBeVisible();
    await expect(page.getByText('Verified — Backend responds; Keycloak discovery is reachable; issuer matches.')).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: /Retry failed requests/ }).click();
    await expect(page.getByText(/Previously observed — Backend responded/)).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.evidence-tier .badge-live')).toHaveCount(0);
    await expect(page.locator('.evidence-tier .stale-chip')).toHaveCount(1);
    await expect(page.getByText('UNVERIFIED IN THIS BROWSER')).toBeVisible();
    await assertNoOverflow(page, 'reports-stale');
    await page.screenshot({ path: 'e2e/screenshots/state-reports-stale.png', fullPage: true });
  });

  test('reports not-verified state (issuer mismatch — never Verified)', async ({ page }) => {
    // IF-V7-01: the two-tier step-1 badges when discovery is
    // reachable but the issuer does not match — NOT VERIFIED, no
    // green badge, release gate still UNVERIFIED IN THIS BROWSER.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.route('**/api/v1/lab/status', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        backend: 'ok',
        issuer: 'http://127.0.0.1:8080/realms/identityforge-lab',
        provider_mode: 'keycloak-local',
        idp: { reachable: true, issuer_matches: false, discovery_url: 'http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration', reason: 'ValueError — discovery issuer differs from the configured issuer' },
        last_verified_login: null,
      }),
    }));
    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Reports & Reviewer Walkthrough' })).toBeVisible();
    await expect(page.getByText(/NOT VERIFIED — IdP reachable but discovery issuer does NOT match/)).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.evidence-tier .badge-live')).toHaveCount(0);
    await expect(page.getByText('UNVERIFIED IN THIS BROWSER')).toBeVisible();
    await assertNoOverflow(page, 'reports-not-verified');
    await page.screenshot({ path: 'e2e/screenshots/state-reports-not-verified.png', fullPage: true });
  });

  test('200% zoom layout equivalent (720 CSS px viewport)', async ({ page }) => {
    // At 200% zoom a 1440px display shows a 720 CSS px viewport, so
    // the 820px responsive breakpoint applies. This test measures
    // that layout directly rather than claiming a browser zoom.
    await page.setViewportSize({ width: 720, height: 450 });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await assertNoOverflow(page, 'zoom200-overview');
    await page.screenshot({ path: 'e2e/screenshots/state-zoom200-overview.png', fullPage: true });
    await page.goto('/scenarios');
    await expect(page.getByRole('listbox', { name: 'Scenarios' })).toBeVisible({ timeout: 15000 });
    await assertNoOverflow(page, 'zoom200-scenarios');
    await page.screenshot({ path: 'e2e/screenshots/state-zoom200-scenarios.png', fullPage: true });
  });

  test('400% zoom layout equivalent (360 CSS px viewport)', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 640 });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await assertNoOverflow(page, 'zoom400-overview');
    await page.screenshot({ path: 'e2e/screenshots/state-zoom400-overview.png', fullPage: true });
  });

  test('increased text size (root font-size 125%)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await page.evaluate(() => { document.documentElement.style.fontSize = '125%'; });
    await assertNoOverflow(page, 'textsize125-overview');
    await page.screenshot({ path: 'e2e/screenshots/state-textsize125-overview.png', fullPage: true });
  });

  test('forced colours (high-contrast) overview', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ forcedColors: 'active' });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await assertNoOverflow(page, 'forced-colors-overview');
    await page.screenshot({ path: 'e2e/screenshots/state-forced-colors-overview.png', fullPage: true });
  });
});
