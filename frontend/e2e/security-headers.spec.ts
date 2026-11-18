import { test, expect } from '@playwright/test';

/**
 * Security headers on the browser-facing app — IF-V8-40 (v8, WS2).
 *
 * Before this fix `vite preview` (the shipped serving path — the
 * frontend Dockerfile CMD is `npm run preview:docker`) sent NO
 * security headers at all on the HTML document or the JS bundle, while
 * the backend API already sent CSP / X-Frame-Options / nosniff /
 * no-referrer / no-store. Any local page could frame the portal
 * (clickjacking) and MIME-sniff its responses. Loopback-only
 * publishing bounds the exposure, so this is Low severity — but the
 * header set is cheap and must match the backend's.
 *
 * Failing-first evidence: curl -sI http://127.0.0.1:5173/ on the
 * untouched v8 tree returned only Vary / Content-Type / Cache-Control
 * / ETag / Date — no CSP, X-Frame-Options, X-Content-Type-Options,
 * Referrer-Policy or Permissions-Policy on `/` or on
 * /assets/index-X2bsjLBG.js (see ws2-v8-evidence/
 * failing-first-preview-headers.txt).
 *
 * The check runs against the LIVE preview server (same stack the
 * screenshots suite uses) and skips cleanly when the lab is not up
 * (a skip is NOT a pass).
 */

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173';

test('preview serves security headers on HTML and JS (IF-V8-40)', async ({ request }) => {
  const html = await request.get(`${BASE}/`);
  if (html.status() !== 200) test.skip(true, 'Lab frontend not reachable — header check NOT RUN.');
  for (const [path, label] of [[`${BASE}/`, 'HTML'], [`${BASE}/assets/index-X2bsjLBG.js`, 'JS bundle']] as const) {
    const res = await request.get(path);
    expect(res.status(), `${label} status`).toBe(200);
    const headers = res.headers();
    expect(headers['content-security-policy'] ?? '', `${label} CSP`).toContain("frame-ancestors 'none'");
    expect(headers['content-security-policy'] ?? '', `${label} CSP`).toContain("default-src 'self'");
    expect(headers['x-frame-options'], `${label} X-Frame-Options`).toBe('DENY');
    expect(headers['x-content-type-options'], `${label} nosniff`).toBe('nosniff');
    expect(headers['referrer-policy'], `${label} Referrer-Policy`).toBe('no-referrer');
    expect(headers['permissions-policy'] ?? '', `${label} Permissions-Policy`).toContain('camera=()');
  }
});
