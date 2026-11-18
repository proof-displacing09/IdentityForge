# IdentityForge — Frontend

Research-console SPA (React 18 + TypeScript + Vite) for the local OAuth/OIDC
attack laboratory. All data is synthetic; no real identities.

## Run

```bash
npm install
npm run dev        # http://127.0.0.1:5173 — proxies /api and /auth to http://127.0.0.1:8000
npm run build      # typecheck + production build
npm test           # Vitest component tests
```

Prerequisite: the backend on 127.0.0.1:8000. Without it, pages show honest
loading / error / NOT RUN states — no fake results are rendered.

## Views

01 Overview · 02 Campus Club Portal · 03 Scenario Studio · 04 Flow Inspector ·
05 Protocol Explorer · 06 Validation Rules · 07 Secure vs Flawed ·
08 Identity & Session Boundaries · 09 Findings & Evidence ·
10 Reports & Walkthrough · 11 Lab Settings · 12 Learning Center

Run history is stored only in the browser (localStorage). Report downloads
(JSON/CSV/Markdown) carry an explicit provenance — never a blanket
"verified":
- `SERVER_VERIFIED_ARTIFACT` — JSON served by the backend
  `/api/v1/runs/{id}/report` endpoint.
- `CLIENT_DERIVED_FROM_SERVER_RUN` — CSV/Markdown assembled in this
  browser from the held run, after the server report was re-fetched
  successfully (the run is server-confirmed; the file was assembled
  locally). Filename contains `CLIENT-DERIVED`; Markdown carries a
  provenance footer.
- `LOCAL_UNSAVED_FALLBACK` — the server report could not be fetched, so
  the file was built from the run object held in this browser only.
  Filename contains `LOCAL-UNSAVED-COPY`; the UI shows a warning next
  to the download. It is not a server-verified report.
Tokens, authorization codes, PKCE verifiers and secrets are never displayed.
