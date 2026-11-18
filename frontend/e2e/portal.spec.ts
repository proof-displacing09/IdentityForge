import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

/**
 * REAL Keycloak browser E2E (P0-10). These specs drive the live stack:
 * browser -> frontend (5173) -> backend (8000) -> Keycloak (8080).
 *
 * They SKIP cleanly (test.skip) when the lab is not reachable, so a
 * missing stack is reported as skipped, never as a fake pass.
 *
 * Required: `docker compose up -d` in the IdentityForge repo, then
 * `npx playwright test`. Base URL from PLAYWRIGHT_BASE_URL, default
 * http://127.0.0.1:5173. Synthetic credentials are the realm's lab
 * accounts (see README): student_01 / LabPass-Student-01!,
 * officer_01 / LabPass-Officer-01!.
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
  test.skip(!(await labReady(request)), 'Lab not reachable: Keycloak IdP is not up (docker compose up -d first). E2E NOT RUN.');
});

async function signInViaKeycloak(page: Page, user: { username: string; password: string }) {
  await page.goto('/portal');
  await page.getByRole('link', { name: /sign in with local identity provider/i }).click();
  // Real Keycloak login page (realm identityforge-lab).
  await expect(page.locator('#username')).toBeVisible({ timeout: 15000 });
  await page.locator('#username').fill(user.username);
  await page.locator('#password').fill(user.password);
  await page.locator('#kc-login').click();
  // Backend callback lands on /portal?login=success.
  await expect(page).toHaveURL(/\/portal\?login=success/, { timeout: 15000 });
  await expect(page.getByText('Signed-in dashboard')).toBeVisible();
  await expect(page.getByText(user.username).first()).toBeVisible();
}

async function apiStatus(page: Page, path: string): Promise<number> {
  return page.evaluate(async (p) => {
    const res = await fetch(p, { credentials: 'include' });
    return res.status;
  }, path);
}

test.describe('real Keycloak login', () => {
  // IF-V4-10 (v5): the discovery issuer is measured test evidence —
  // the E2E gate requires this test passed before marking real E2E
  // PASS. It fetches the discovery document directly (no browser)
  // and asserts the exact pinned canonical issuer; a wrong issuer
  // (stale stack, wrong realm, proxy rewrite) fails the test instead
  // of silently running logins against the wrong IdP.
  test('Keycloak discovery issuer is the pinned canonical issuer', async ({ request }) => {
    const res = await request.get('http://127.0.0.1:8080/realms/identityforge-lab/.well-known/openid-configuration');
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.issuer).toBe('http://127.0.0.1:8080/realms/identityforge-lab');
  });

  test('student_01: member 200, officer 403', async ({ page }) => {
    await signInViaKeycloak(page, STUDENT);
    expect(await apiStatus(page, '/api/v1/portal/member')).toBe(200);
    expect(await apiStatus(page, '/api/v1/portal/officer')).toBe(403);
    await expect(page.getByRole('button', { name: /load officer resource/i })).toBeVisible();
    await page.getByRole('button', { name: /load officer resource/i }).click();
    await expect(page.getByText(/denied/i).first()).toBeVisible();
  });

  test('logout revokes the session; stale cookie is denied (401)', async ({ page }) => {
    await signInViaKeycloak(page, STUDENT);
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(200);
    await page.getByRole('button', { name: /^log out$/i }).click();
    await expect(page.getByText('You are not signed in')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
    expect(await apiStatus(page, '/api/v1/portal/member')).toBe(401);
  });

  test('officer_01: member 200 and officer 200', async ({ page }) => {
    await signInViaKeycloak(page, OFFICER);
    expect(await apiStatus(page, '/api/v1/portal/member')).toBe(200);
    expect(await apiStatus(page, '/api/v1/portal/officer')).toBe(200);
    await page.getByRole('button', { name: /load officer resource/i }).click();
    await expect(page.getByLabel('Officer resource')).toBeVisible();
  });

  test('deep link and refresh keep the portal view and session', async ({ page }) => {
    await signInViaKeycloak(page, STUDENT);
    await page.goto('/scenarios');
    await expect(page.getByText('Scenario Studio', { exact: false }).first()).toBeVisible();
    await page.goto('/portal');
    await expect(page.getByText('Signed-in dashboard')).toBeVisible();
    await page.reload();
    await expect(page.getByText('Signed-in dashboard')).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/scenarios/);
  });

  test('callback error path shows a safe reason, no session', async ({ page }) => {
    await page.goto('/?error=STATE_MISMATCH');
    await expect(page.getByText(/Sign-in failed/)).toBeVisible();
    await expect(page.getByText('STATE_MISMATCH')).toBeVisible();
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(401);
  });

  test('logout without a CSRF token is rejected 403 and the session survives', async ({ page }) => {
    await signInViaKeycloak(page, STUDENT);
    const status = await page.evaluate(async () => {
      const res = await fetch('/auth/logout', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      return res.status;
    });
    expect(status).toBe(403);
    expect(await apiStatus(page, '/api/v1/portal/me')).toBe(200);
  });

  test('unknown route renders the 404 view', async ({ page }) => {
    await page.goto('/no-such-view');
    await expect(page.getByText('Page not found')).toBeVisible();
  });
});
