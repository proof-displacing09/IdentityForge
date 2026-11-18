import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Accessibility (axe) scans — Trustline Atelier v3 (P2-19).
 *
 * ZERO-TOLERANCE contract: the suite fails on ANY automated axe
 * violation at ANY impact level (minor, moderate, serious, critical)
 * on every tested view and state. There are no approved exceptions;
 * if one is ever needed it must be listed here with a justification
 * and an explicit count — never silently tolerated.
 *
 * Coverage: all 12 routes, signed-in student AND officer, the reset
 * confirmation dialog, validation-error state, the Atlas inspector
 * (node expanded), the mobile menu open at 320px, focus order, the
 * loading state, and the reduced-motion preference.
 *
 * Scans run against the LIVE stack (frontend preview on 5173, backend
 * 8000, Keycloak 8080). Skips cleanly when the lab is not reachable
 * (a skip is NOT a pass).
 */

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173';
const API = BASE.replace(':5173', ':8000');
const STUDENT = { username: 'student_01', password: 'LabPass-Student-01!' };
const OFFICER = { username: 'officer_01', password: 'LabPass-Officer-01!' };

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
  test.skip(!(await labReady(request)), 'Lab not reachable: Keycloak IdP is not up. Axe scan NOT RUN.');
});

/** Zero-tolerance scan: ANY violation (any impact) fails the test. */
async function scan(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).analyze();
  for (const v of results.violations) {
    console.log(`axe ${label}: ${v.id} (${v.impact}) — ${v.description} — ${v.nodes.length} node(s)`);
  }
  expect(results.violations, `${label}: axe violations (zero-tolerance):\n${JSON.stringify(results.violations, null, 2)}`).toEqual([]);
  console.log(`axe ${label}: 0 violations`);
}

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

test.describe('axe scans — all views', () => {
  test('Overview', async ({ page }) => {
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await scan(page, 'overview');
  });

  test('Portal signed-out', async ({ page }) => {
    await page.goto('/portal');
    await expect(page.getByText('You are not signed in')).toBeVisible();
    await scan(page, 'portal-signed-out');
  });

  test('Portal signed-in (student_01)', async ({ page }) => {
    await signInViaKeycloak(page, STUDENT);
    await scan(page, 'portal-signed-in-student');
  });

  test('Portal signed-in (officer_01)', async ({ page }) => {
    await signInViaKeycloak(page, OFFICER);
    await scan(page, 'portal-signed-in-officer');
  });

  test('Scenario Studio', async ({ page }) => {
    await page.goto('/scenarios');
    await expect(page.getByRole('heading', { name: 'Scenario Studio' })).toBeVisible();
    await expect(page.getByRole('listbox', { name: 'Scenarios' })).toBeVisible({ timeout: 15000 });
    await scan(page, 'scenarios');
  });

  test('Scenario Studio — validation error state (I6 rejected)', async ({ page }) => {
    await runScenario(page, 'I6');
    await expect(page.getByText('WRONG_AUDIENCE').first()).toBeVisible();
    await scan(page, 'scenarios-i6-error');
  });

  test('Flow Inspector (Atlas, after a real I6 run)', async ({ page }) => {
    await runScenario(page, 'I6');
    await page.goto('/flow');
    await expect(page.getByRole('heading', { name: /Flow Inspector/ })).toBeVisible();
    await expect(page.getByText('ID token verified')).toBeVisible();
    await scan(page, 'flow');
  });

  test('Flow Inspector — Atlas inspector expanded', async ({ page }) => {
    await runScenario(page, 'I6');
    await page.goto('/flow');
    await expect(page.getByRole('heading', { name: /Flow Inspector/ })).toBeVisible();
    // Expand the ID-token-verified Atlas node to open the inspector region.
    const node = page.getByRole('button', { name: /ID token verified/ }).first();
    await node.click();
    await expect(page.getByRole('region', { name: /Details for/ })).toBeVisible();
    await scan(page, 'flow-inspector-open');
  });

  test('Flow Inspector — Live Keycloak namespace', async ({ page }) => {
    await signInViaKeycloak(page, STUDENT);
    await page.goto('/flow');
    await expect(page.getByRole('heading', { name: /Flow Inspector/ })).toBeVisible();
    await page.getByRole('button', { name: 'Live Keycloak logins' }).click();
    await expect(page.getByText('SESSION_CREATED').first()).toBeVisible({ timeout: 15000 });
    await scan(page, 'flow-live');
  });

  test('Protocol Explorer', async ({ page }) => {
    await page.goto('/protocol');
    await expect(page.getByRole('heading', { name: 'Protocol Explorer' })).toBeVisible();
    await scan(page, 'protocol');
  });

  test('Validation Rules', async ({ page }) => {
    await page.goto('/rules');
    await expect(page.getByRole('heading', { name: 'Validation Rules' })).toBeVisible();
    await scan(page, 'rules');
  });

  test('Secure vs Flawed', async ({ page }) => {
    await runScenario(page, 'I6');
    await page.goto('/compare');
    await expect(page.getByRole('heading', { name: 'Secure vs Flawed' })).toBeVisible();
    await scan(page, 'compare');
  });

  test('Identity & Session Boundaries', async ({ page }) => {
    await page.goto('/boundaries');
    await expect(page.getByRole('heading', { name: 'Identity & Session Boundaries' })).toBeVisible();
    await scan(page, 'boundaries');
  });

  test('Findings & Evidence', async ({ page }) => {
    await runScenario(page, 'I1');
    await page.goto('/findings');
    await expect(page.getByRole('heading', { name: 'Findings & Evidence' })).toBeVisible();
    await scan(page, 'findings');
  });

  test('Reports & Walkthrough', async ({ page }) => {
    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Reports & Reviewer Walkthrough' })).toBeVisible();
    await scan(page, 'reports');
  });

  test('Lab Settings', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Lab Settings' })).toBeVisible();
    await scan(page, 'settings');
  });

  test('Lab Settings — reset confirm dialog (officer)', async ({ page }) => {
    // The reset dialog is officer-only: sign in as officer first.
    await signInViaKeycloak(page, OFFICER);
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Lab Settings' })).toBeVisible();
    await page.getByRole('button', { name: /Reset lab state/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await scan(page, 'settings-reset-dialog');
    // Cancel — never confirm here (confirming would wipe backend
    // evidence for other tests).
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });

  test('Learning Center', async ({ page }) => {
    await page.goto('/learn');
    await expect(page.getByRole('heading', { name: 'Learning Center' })).toBeVisible();
    await scan(page, 'learn');
  });
});

test.describe('axe scans — states and preferences', () => {
  test('Mobile menu open at 320px', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await page.locator('.menu-btn').click();
    await expect(page.getByRole('navigation', { name: 'IdentityForge sections' })).toBeVisible();
    await scan(page, 'mobile-menu-open');
  });

  test('Overview with reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await scan(page, 'overview-reduced-motion');
  });

  test('Settings — identity check fails (500): unknown-identity state, reset disabled', async ({ page }) => {
    // P2-23 (v4): the unknown-identity state must itself be accessible
    // — the retry button is present and the reset stays disabled.
    await page.route('**/api/v1/portal/me', (route) => route.fulfill({ status: 500, body: 'boom' }));
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Lab Settings' })).toBeVisible();
    await expect(page.getByText(/returned a server error/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: /Retry identity check/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Reset lab state/ })).toBeDisabled();
    await scan(page, 'settings-identity-unknown');
  });

  test('Overview error state with retry', async ({ page }) => {
    await page.route('**/api/v1/lab/status', (route) => route.fulfill({ status: 500, body: 'boom' }));
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByText(/Lab status failed/)).toBeVisible();
    await expect(page.getByRole('button', { name: /Retry loading lab status/ })).toBeVisible();
    await scan(page, 'overview-error-retry');
  });

  test('Atlas keyboard traversal: arrow keys move between stages', async ({ page }) => {
    await runScenario(page, 'I6');
    await page.goto('/flow');
    await expect(page.getByRole('heading', { name: /Flow Inspector/ })).toBeVisible();
    await expect(page.getByText('ID token verified')).toBeVisible();
    const first = page.getByRole('button', { name: /Sign-in started/ }).first();
    await first.focus();
    await expect(first).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('button', { name: /Identity provider authenticates/ }).first()).toBeFocused();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('button', { name: /Callback returned/ }).first()).toBeFocused();
    await page.keyboard.press('ArrowLeft');
    await expect(page.getByRole('button', { name: /Identity provider authenticates/ }).first()).toBeFocused();
    await page.keyboard.press('ArrowUp');
    await expect(first).toBeFocused();
  });

  test('Overview loading state', async ({ page }) => {
    // Delay the status call so the skeleton loading state is on screen.
    await page.route('**/api/v1/lab/status', async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      await route.continue();
    });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await scan(page, 'overview-loading');
  });

  test('Focus order: skip link first, then the menu button at 320px', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.goto('/overview');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeFocused();
    // Skip link actually moves focus to main content.
    await page.keyboard.press('Shift+Tab');
    await page.getByRole('link', { name: 'Skip to main content' }).click();
    await expect(page.getByRole('main')).toBeFocused();
  });
});
