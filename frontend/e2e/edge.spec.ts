import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

/**
 * Edge-case browser tests (real Keycloak, live stack).
 *
 * - Provider error callback (?error=...) shows a safe reason, no session.
 * - User cancels at the Keycloak login page (skipped with a reason when
 *   this realm's login page offers no cancel control).
 * - Browser back after logout lands on a signed-out portal.
 * - Unknown/expired state at the callback is rejected (STATE_REUSED —
 *   the backend has no live transaction for the presented state).
 * - Second callback replay is rejected (STATE_REUSED) via the real
 *   browser flow: the callback URL is captured during sign-in, then
 *   navigated to a second time.
 *
 * Skips cleanly when the lab is not reachable (a skip is NOT a pass).
 */

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173';
const API = BASE.replace(':5173', ':8000');
const STUDENT = { username: 'student_01', password: 'LabPass-Student-01!' };

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
  test.skip(!(await labReady(request)), 'Lab not reachable: Keycloak IdP is not up. Edge E2E NOT RUN.');
});

async function apiStatus(page: Page, path: string): Promise<number> {
  return page.evaluate(async (p) => {
    const res = await fetch(p, { credentials: 'include' });
    return res.status;
  }, path);
}

async function signInViaKeycloak(page: Page) {
  await page.goto('/portal');
  await page.getByRole('link', { name: /sign in with local identity provider/i }).click();
  await expect(page.locator('#username')).toBeVisible({ timeout: 15000 });
  await page.locator('#username').fill(STUDENT.username);
  await page.locator('#password').fill(STUDENT.password);
  await page.locator('#kc-login').click();
  await expect(page).toHaveURL(/\/portal\?login=success/, { timeout: 15000 });
  await expect(page.getByText('Signed-in dashboard')).toBeVisible();
}

test.describe('mobile drawer keyboard (320px, P2-18)', () => {
  test('menu button controls the sidebar nav; Escape closes and focus returns', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    const menu = page.locator('.menu-btn');
    await expect(menu).toBeVisible();
    // aria-controls must name the real sidebar nav, not #main.
    await expect(menu).toHaveAttribute('aria-controls', 'sidebar-nav');
    await expect(page.locator('#sidebar-nav')).toHaveAttribute('aria-label', 'IdentityForge sections');
    // Keyboard-only: Tab past the skip link lands on the menu button
    // (a closed drawer leaves the tab order — P2-18).
    await page.keyboard.press('Tab'); // skip link
    await page.keyboard.press('Tab'); // menu button
    await expect(menu).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('navigation', { name: 'IdentityForge sections' })).toBeVisible();
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
    // Focus moved into the drawer; Escape closes and returns focus.
    await page.keyboard.press('Escape');
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await expect(menu).toBeFocused();
    // Closed drawer is out of the tab order: Tab from the button goes
    // to Details, then Refresh status — not into hidden nav links.
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Details' })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Refresh status' })).toBeFocused();
  });
});

test.describe('login edge cases', () => {
  test('provider error callback shows a safe reason, no session', async ({ page }) => {
    await page.goto('/?error=PROVIDER_ERROR');
    await expect(page.getByText(/Sign-in failed/)).toBeVisible();
    await expect(page.getByText('PROVIDER_ERROR')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('user cancels at the Keycloak login page', async ({ page }) => {
    await page.goto('/portal');
    await page.getByRole('link', { name: /sign in with local identity provider/i }).click();
    await expect(page.locator('#username')).toBeVisible({ timeout: 15000 });
    // Keycloak's login page exposes a cancel control only when the
    // authentication flow supports it; if this realm offers none, the
    // case cannot be driven in the browser and is skipped, not faked.
    const cancel = page.locator('#kc-cancel, a:has-text("Cancel"), button:has-text("Cancel")').first();
    const hasCancel = await cancel.isVisible().catch(() => false);
    test.skip(!hasCancel, 'Keycloak login page offers no cancel control in this realm — cancel path NOT RUN.');
    await cancel.click();
    // Cancelling returns to the frontend with a provider error (or to
    // the portal with no session); either way no session must exist.
    await expect(page).toHaveURL(/\?error=|portal/, { timeout: 15000 });
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('browser back after logout shows the signed-out portal', async ({ page }) => {
    await signInViaKeycloak(page);
    await page.getByRole('button', { name: /^log out$/i }).click();
    await expect(page.getByText('You are not signed in')).toBeVisible();
    await page.goto('/scenarios');
    await expect(page.getByRole('heading', { name: 'Scenario Studio' })).toBeVisible();
    await page.goBack();
    await expect(page.getByText('You are not signed in')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('unknown state at the callback is rejected (STATE_REUSED)', async ({ page }) => {
    await page.goto('/auth/callback?state=does-not-exist&code=whatever');
    await expect(page).toHaveURL(/\/\?error=STATE_REUSED/, { timeout: 15000 });
    await expect(page.getByText(/Sign-in failed/)).toBeVisible();
    await expect(page.getByText('STATE_REUSED')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('missing state parameter is rejected (STATE_MISSING)', async ({ page }) => {
    // No state parameter at all: the presence check fires first
    // (IF-V8-02, v8 — the duplicate/malformed guard used to fire
    // first and report CALLBACK_MALFORMED, which made the
    // STATE_MISSING branch unreachable dead code).
    await page.goto('/auth/callback?code=whatever');
    await expect(page).toHaveURL(/\/\?error=STATE_MISSING/, { timeout: 15000 });
    await expect(page.getByText('STATE_MISSING')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('empty state is rejected (STATE_MISSING)', async ({ page }) => {
    await page.goto('/auth/callback?state=&code=whatever');
    await expect(page).toHaveURL(/\/\?error=STATE_MISSING/, { timeout: 15000 });
    await expect(page.getByText('STATE_MISSING')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('second callback replay is rejected (STATE_REUSED)', async ({ page }) => {
    let callbackUrl: string | null = null;
    const seen = new Promise<void>((resolve) => {
      page.on('request', (req) => {
        if (req.url().includes('/auth/callback?')) {
          callbackUrl = req.url();
          resolve();
        }
      });
    });
    await signInViaKeycloak(page);
    await seen;
    expect(callbackUrl).not.toBeNull();
    // The transaction was consumed by the first callback; replay it.
    await page.goto(callbackUrl!);
    await expect(page).toHaveURL(/\/\?error=STATE_REUSED/, { timeout: 15000 });
    await expect(page.getByText('STATE_REUSED')).toBeVisible();
  });
});

test.describe('findings download provenance (IF-V4-12)', () => {
  test('CSV is labelled CLIENT-DERIVED and JSON is a server artifact', async ({ page }) => {
    // Run I1 in the Studio so there is a real run to download.
    await page.goto('/scenarios');
    await expect(page.getByRole('listbox', { name: 'Scenarios' })).toBeVisible({ timeout: 15000 });
    await page.getByRole('option', { name: /^I1\b/ }).click();
    await page.getByRole('button', { name: /^Run I1$/ }).click();
    await expect(page.getByText('Session & model state').first()).toBeVisible({ timeout: 30000 });

    await page.goto('/findings');
    await expect(page.getByRole('heading', { name: 'Findings & Evidence' })).toBeVisible();

    const csvPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'CSV' }).first().click();
    const csvDownload = await csvPromise;
    expect(csvDownload.suggestedFilename()).toContain('CLIENT-DERIVED');
    expect(csvDownload.suggestedFilename()).toContain('I1-');
    await expect(page.getByText(/Client-derived report/)).toBeVisible();

    const jsonPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'JSON' }).first().click();
    const jsonDownload = await jsonPromise;
    expect(jsonDownload.suggestedFilename()).toMatch(/^I1-[a-z0-9-]+\.json$/);
    expect(jsonDownload.suggestedFilename()).not.toContain('LOCAL-UNSAVED-COPY');
    // IF-V6-01 (v7): the download now also renders a status notice whose
    // text starts "Server-verified artifact — downloaded from …", so the
    // regex would match two elements (strict-mode violation). Assert the
    // legend label exactly instead; the notice is covered by the
    // Findings unit tests on the fallback/notice copy.
    await expect(page.getByText('Server-verified artifact', { exact: true })).toBeVisible();
  });
});
