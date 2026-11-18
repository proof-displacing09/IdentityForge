import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Minimal typing for the one Node API used here (no @types/node in the
// lockfile); avoids pulling a new dependency just for BACKEND_URL.
declare const process: { env: Record<string, string | undefined> }

// Backend base for the Vite dev proxy (server-side setting, P0-04):
// BACKEND_URL=http://backend:8000 in Compose (Docker service DNS),
// http://127.0.0.1:8000 for standalone local dev. The browser never
// needs a hard-coded backend origin: it uses same-origin /api and /auth.
import type { Plugin } from 'vite'

const backendTarget = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

// IF-V8-40 (v8, WS2): the browser-facing app must carry the same
// security-header discipline as the backend API (which already sends
// CSP / X-Frame-Options / nosniff / no-referrer / no-store). Before
// this fix `vite preview` — the shipped serving path (frontend
// Dockerfile CMD `npm run preview:docker`) — sent NO security headers
// at all on the HTML or the JS bundle, so any local page could frame
// the portal (clickjacking) and MIME-sniff its responses. Loopback-only
// publishing bounds the exposure, but the header set is cheap and
// must match the backend's. Applied to BOTH the dev server and the
// preview server so no serving path silently loses it.
// CSP notes: the app fetches same-origin /api + /auth only
// (connect-src 'self'); top-level Keycloak redirects are navigations,
// not fetches, so they are unaffected. No inline <script> exists;
// style-src keeps 'unsafe-inline' only so Vite dev HMR <style>
// injection keeps working — the built bundle uses a CSS file.
const SECURITY_HEADERS: Record<string, string> = {
  'content-security-policy':
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; " +
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
  'x-frame-options': 'DENY',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'permissions-policy': 'camera=(), microphone=(), geolocation=()',
}

function securityHeadersPlugin(): Plugin {
  const apply = (server: { middlewares: { use: (fn: (req: unknown, res: { setHeader: (k: string, v: string) => void }, next: () => void) => void) => void } }) => {
    server.middlewares.use((_req, res, next) => {
      for (const [name, value] of Object.entries(SECURITY_HEADERS)) res.setHeader(name, value)
      next()
    })
  }
  return {
    name: 'identityforge-security-headers',
    configureServer(server) { apply(server) },
    configurePreviewServer(server) { apply(server) },
  }
}

export default defineConfig({
  plugins: [react(), securityHeadersPlugin()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: false },
      '/auth': { target: backendTarget, changeOrigin: false },
    },
  },
  // Production serving (P0-04): `vite preview` serves dist/ with the
  // same /api + /auth reverse proxy. Explicit (not inherited) so the
  // Docker entry point cannot silently lose the proxy.
  preview: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: false },
      '/auth': { target: backendTarget, changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // Playwright specs live in e2e/ and must not be collected by Vitest.
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
