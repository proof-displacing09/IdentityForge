# UI Design System — IdentityForge // Trustline Atelier

Status: implemented in `frontend/src/styles.css` (216 lines) and
`frontend/src/components/ui.tsx`; verified 2026-11-11 by `npm run
typecheck` (PASS), Vitest **64/64** (8 files), `npm run build` (JS
**165.14 kB / 53.71 kB gzip** with 14 JS assets — index + 13 lazy
chunks), Playwright **62 passed, 1 skipped** (portal 7/7,
edge 7/7 + 1 honest skip, axe 25/25, screenshots 23/23), axe
**25/25 tests, 0 violations at any impact level (zero-tolerance)**,
and **99 screenshots, all fresh v4**, inspected at 6 viewports
(320×740, 390×844, 768×1024, 1280×800, 1440×900, 1920×1080). This
document describes what is actually shipped, not an aspiration. It
replaces the Trustline-era system (graphite/teal) in full. Atelier v4
changes are marked **(v4)** below; v3 numbers are kept only where
they are history.

## 1. Product identity

- **Brand lockup:** "IdentityForge // Operation Trustline" — a 34 px
  brass-bordered `IF` mark (monospace, brass on ink) plus wordmark
  with a brass accent, in the sidebar; the subtitle "Operation
  Trustline" is always present so the lab is never mistaken for a
  production identity product.
- **Voice:** quiet, data-rich, editorial — an atelier, not a
  dashboard. No neon-hacker clichés, no glowing gradients, no
  decorative charts, no fake security scores, no emoji. Every number
  on screen comes from a recorded run, a measured health probe, or a
  labelled fixture — never an invented metric.

## 2. Design tokens (`:root` in `styles.css`)

| Token | Value | Use |
| --- | --- | --- |
| `--ink` | `#090E15` | Page background (deep ink) |
| `--surface` / `--surface-2` / `--surface-3` | `#111924` / `#16202F` / `#1D2A3C` | Layered cards, sidebar, hover states |
| `--border` / `--border-strong` | `#232F42` / `#35445C` | 1 px hairline borders |
| `--platinum` | `#C7D0DC` | Trim, secondary emphasis |
| `--text` / `--muted` / `--faint` | `#EFEAE2` / `#A9B2C8` / `#98A3B5` | Porcelain body / secondary / tertiary text |
| `--teal` / `--teal-dim` | `#4FAE9E` / `#2E7D72` | Muted jewel teal — **verified identity only** |
| `--azure` / `--azure-dim` | `#7FB0E6` / `#4E7FB0` | Icy blue — routes, data, links |
| `--brass` / `--brass-dim` | `#C9A24B` / `#8F7130` | Gold/brass — the selected, the important |
| `--amber` | `#D9A441` | Warning / blocked states only |
| `--red` | `#E06C6C` | **Red ONLY for an actual denial or failure** |
| `--green` | `#58B98A` | **Green ONLY for a measured success** |
| `--radius` / `--radius-sm` | `10px` / `6px` | Cards / small controls |
| Spacing | `4 / 8 / 12 / 16 / 24 / 32 / 48 px` | `--sp-1` … `--sp-12` |
| `--font-sans` | system sans stack | UI text |
| `--font-mono` | system monospace stack | Identifiers, run IDs, claim names, metrics |

Contrast (measured against the shipped tokens): porcelain
`#EFEAE2` on ink `#090E15` ≈ 15:1; muted `#A9B2C0` on surface
`#111924` ≈ 7:1. `.faint` was lightened `#7E8898` → `#98A3B5`
during the axe pass because the old value failed contrast for the
"· not run" text. Selected/active states never depend on colour
alone — the active nav item also gets bold text and a brass border,
the active scenario button also gets bold text.

Focus is a 2 px brass `:focus-visible` outline. Motion is
150 ms ease transitions only; `prefers-reduced-motion: reduce`
disables animation/transition. No animation blocks a button or a
test timing path.

## 3. Layout

- **Shell:** `.app` flex row; sticky sidebar (276 px, collapsible to
  78 px via `.sidebar-toggle`), `.main` max-width 1180 px.
- **Top bar (v3):** sticky, blurred (`rgba(9,14,21,.96)`), shows
  environment and ONE hierarchical readiness pill (`Ready — IdP
  verified` in teal / `Not ready — <reason>` / `Lab status
  unavailable`) plus a `Details` toggle that opens an expandable
  diagnostics region (backend, issuer, provider mode, IdP
  reachability + issuer match, discovery URL, **evidence health**
  from `lab/status.evidence`, last verified login, and an honest
  "live gates not measured in this browser" line). The old
  multi-badge status wall is gone. When the environment is down,
  the error UI is clearly nonfunctional and points to `doctor`.
  Last verified login still comes from `GET /api/v1/lab/status` —
  never a hardcoded claim. Unknown login state renders as NOT RUN.
- **Sidebar nav (v3):** 12 custom inline-SVG glyphs (no icon font,
  no emoji); the menu button uses `aria-controls="sidebar-nav"`
  (P2-18 — the old `aria-controls="main"` pointed at the wrong
  element); a closed drawer leaves the tab order and accessibility
  tree (`visibility:hidden` under 1024 px).
- **Page headings:** `h1` 1.65 rem + `.page-sub` purpose line (max
  72 ch) on every view, with a brass `.eyebrow` kicker above;
  contextual actions sit in the same header row.
- **Responsive:** below 820 px the sidebar becomes a 276 px
  full-height drawer (`.menu-btn`, `.drawer-backdrop`,
  `overflow:auto` so every nav item is reachable); `.compare-grid`
  and `.kv` collapse to one column; tables scroll inside
  `.table-wrap` (`min-width: 880px`, so chips such as
  `WRONG_AUDIENCE` never wrap mid-word). Verified layouts at **6
  widths: 320, 390, 768, 1280, 1440, 1920**, with no horizontal page
  scroll at any viewport — enforced by a PROGRAMMATIC overflow
  assertion (`scrollWidth <= innerWidth`) on every screenshot
  (v3, `e2e/screenshots.spec.ts`). At 320 px the status wall is ONE
  compact priority status row + expandable diagnostics (v3 P2-20).
- **Long strings:** `.code` uses `overflow-wrap: anywhere` (breaks
  at spaces first, still breaks unbreakable strings); the old
  `word-break: break-all` was removed after screenshots showed it
  splitting words mid-syllable ("wron g", "identit yforge-lab").

## 4. Shared components (`src/components/ui.tsx`)

- `StatusPill` — tones `ok | warn | bad | info | neutral` **plus
  `teal` (v3, verified identity only)**, with a dot plus text
  (never colour-only).
- `MetricTile` — label / value (monospace) / note.
- `EmptyState`, `Skeleton`, `RunStatusRow` (status + mode badge).
- `ConfirmDialog` — focus handling + ESC to cancel; used for lab reset.
- `Toast` — `error | info`, dismissible.
- CSS-only primitives in `styles.css`: `.card`, `.btn` (+ `.btn-teal`,
  `.btn-ghost`, `.btn-danger`), `.badge-*` (`pass`, `fail`/`error`,
  `skipped`/`notrun`, `running`, `mode`, `fixture`), `.pill-*`,
  `.metric`, `.kv`, `.timeline` (`.rejected` red rail, `.notrun`
  dimmed), `.alert-*`, `.modal`, `.toast`, `.empty`.

Every component has genuine hover, focus (brass 2 px outline),
disabled (`.btn:disabled` 50 % opacity, `cursor: not-allowed`),
loading (skeleton) and error states. There are no dummy clickable
controls: a button that cannot act is disabled with a reason, not
decorative.

## 5. Routes (`src/router.ts`)

Real history routing — `<a href>` + `pushState`/`popstate` in
`src/App.tsx`. Deep link, refresh, back/forward all land on the right
view; unknown paths render a 404 view with a working link home.
`/` redirects to `/overview`.

| Path | View |
| --- | --- |
| `/overview` | Command center |
| `/portal` | Cedarbridge Campus Club portal |
| `/scenarios` | Scenario Studio (I1–I18) |
| `/flow` | Flow Inspector / Identity Transaction Atlas |
| `/protocol` | Protocol Explorer |
| `/rules` | Validation Rules |
| `/compare` | Secure vs Flawed |
| `/boundaries` | Identity & Session Boundaries |
| `/findings` | Findings & Evidence |
| `/reports` | Reports & Reviewer Walkthrough |
| `/settings` | Lab Settings |
| `/learn` | Learning Center |

Login callback lands on `/portal?login=success`, which shows a
confirmation banner; the session itself is confirmed by `GET
/portal/me`, not by the query string. `/?error=REASON` shows a safe
reason-code banner (no secret payloads).

## 6. Identity Transaction Atlas (`FlowInspector.tsx` + `.atlas-*`)

**Seven stages (v4)** across the actors browser → BFF → Keycloak →
validator → session/policy → resource, driven ONLY by recorded
events: the selected run's recorded timeline merged with
`GET /api/v1/runs/{id}/events`, plus the run's recorded
`resource_access_outcome` verbatim, and live `AUTHORIZATION_DECISION`
events from `GET /api/v1/live-logins`. Nothing is fabricated: a
stage with no recorded event is NOT OBSERVED, never invented.

Stage vocabulary (v4, `FlowInspector.tsx:36`): VERIFIED / DENIED /
ERROR / NOT REACHED / FIXTURE-ONLY / NOT OBSERVED / NOT RUN. Pill
mapping (`FlowInspector.tsx:345`): VERIFIED → `badge-pass` (green —
deliberately NOT teal, because a fixture step can be VERIFIED
without being a real verified identity), DENIED / ERROR →
`badge-fail` (red), NOT OBSERVED → `badge-brass` (a gap in the
record), FIXTURE-ONLY → `badge-fixture` (azure), NOT REACHED /
NOT RUN → `badge-notrun` (muted). Each node shows its observed
status with at-time metadata; clicking a node (or keyboard-focusing
it) opens an inspector: Recorded at (timestamp), Provenance
(LIVE_KEYCLOAK / OFFLINE_FIXTURE), and "Flawed fixture omitted
check" (the exact guard name per fixture). A rejected node stops
the flow: later nodes are forced to NOT RUN and the connector turns
red. Offline-fixture runs show the browser-start / callback /
code-exchange stages as FIXTURE-ONLY (fixtures mint test tokens
directly and never perform them — verified by executing the real
backend: `run_scenario('I1')` → `[TOKEN_VERIFIED ok,
SESSION_CREATED ok]`, `run_scenario('I6')` → `[TOKEN_VERIFIED
rejected]` only) and are labelled OFFLINE FIXTURE, never presented
as a live login. The fixture resource stage is synthesized from
`resource_access_outcome` verbatim (both allowed → VERIFIED,
only-denied → DENIED `POLICY_DENIED`, `no_session` /
`session_created` → no pseudo-step). Reason codes render on their
own line with `<wbr/>` after each underscore
(`FlowInspector.tsx:341-343`) so `WRONG_AUDIENCE` wraps as `WRONG_`
/ `AUDIENCE`, never mid-word — the DOM text stays the verbatim code.
Horizontal flow at ≥1024 px, vertical story below; full text
alternative ("Full timeline — text alternative to the diagram");
keyboard navigable (Arrow keys move between stages; each node is a
`<button>` with `aria-expanded`).

**v2 addition — LIVE_KEYCLOAK namespace:** the Atlas also renders
redacted live-login timelines from `GET /api/v1/live-logins`
(`LIVE_KEYCLOAK` provenance, subjects stored as SHA-256 hash +
synthetic username, no codes/tokens/verifiers). Live and offline
timelines are visually and textually separate; a live timeline is
never merged into an offline run's evidence.

## 7. Truthfulness rules (enforced in UI code, not just docs)

- Status badges come from measured endpoints (`/api/v1/lab/status`,
  `/api/v1/runs/{id}`), never from a container being up or a page
  rendering. A running Keycloak is not a login test.
- **ModeBadge rule (v4, P2-23):** teal (`badge-live`) is reserved
  ONLY for a real Keycloak-verified identity; azure
  (`badge-fixture`) is for offline fixture / protocol data. The v3
  mapping was backwards (real → azure, fixture → teal) and was
  corrected in v4 (`src/components/Badge.tsx:21`,
  `src/styles.css:106-113`); `Badge.test.tsx` asserts the classes
  (real → `badge-live`, fixture → `badge-fixture`, never the
  reverse). Atlas VERIFIED pills are green (`badge-pass`), not
  teal — a fixture step can be VERIFIED without being a real
  verified identity (see §6).
- `evidence_saved === false` surfaces a visible warning in Scenario
  Studio and Findings; a report is never shown as persisted when it
  was not. When the backend report endpoint does not respond, the
  fallback download is labelled **LOCAL UNSAVED COPY** — never a
  silent substitute.
- CSV exports neutralise spreadsheet formula injection: cells
  starting with `=`, `+`, `-`, `@` are prefixed with a single quote.
- Protocol Explorer shows only metadata that exists in the selected
  run. The single illustrative authorization-URL example is labelled
  **SAMPLE**; the old `eyJ…` / `code-placeholder` strings were removed.
- Secure vs Flawed renders one selected real run: identical synthetic
  input, secure decision vs one-check-missing flawed decision, with
  run ID, mode, timestamp and provenance, plus the explicit note that
  a fixture returning ALLOW is not an exploitation finding. The v2
  run fields (`session_preexisted`, `session_revoked`,
  `flawed_model_status`, `flawed_observed_result`,
  `protected_resource_disclosed`, `evidence_provenance`) are shown
  where they exist.
- Logout shows success **only** on backend 200; on failure the UI
  keeps the signed-in state and shows the error. Portal logout copy
  states it is **app-local only — not an IdP SSO logout**. Reset
  reports the real backend outcome (403 = nothing cleared; 401 =
  not signed in; 422 = confirmation missing) and shows the operator
  identity and the counts that would be cleared from
  `GET /api/v1/lab/counts` (v3 P0-01); on success it shows the
  cleared counts and states the officer's own session was revoked.
- **Settings identity states (v4, P2-23):** `meState` is `checking |
  signed-in | signed-out | forbidden | unreachable | server-error`
  (`Settings.tsx:30`); 401 → signed-out ("session expired"), 403 →
  forbidden (deliberately NOT claiming a signed-in identity — the
  backend `/portal/me` only ever returns 401 for unauthenticated,
  so a 403 cannot prove who is signed in), network failure →
  unreachable, 5xx → server-error. A "Retry identity check" button
  re-runs the check. The reset button is enabled ONLY on a measured
  officer identity (`identityUnknown`, line 113).
- **Reviewer path (v3 P2-23):** Overview and Reports carry an
  8-step guided 5–10 minute path (start services → secure student
  sign-in → deny officer → officer sign-in → run I1–I18 → inspect
  live Atlas events → compare one missing-check model → export
  redacted evidence). Each step shows `Verified` only from
  browser-held evidence, otherwise `Not run yet` or an action step.
  Reports offers a privacy-safe **portfolio evidence summary**
  download (counts, per-scenario latest outcomes, live-login counts
  + synthetic usernames only, gates-not-measured note, explicit
  authorship note: the lab was built with AI-assisted development;
  sole manual authorship is NOT claimed).
- **Portal crest (v3 P2-23):** the Campus Club Portal carries a
  distinct crest (shield + open book) so Cedarbridge (friendly
  campus identity) and Trustline (precise forensic console) read as
  two harmonious surfaces, not one generic dashboard.
- **Performance (v3 P2-24):** route-level `React.lazy` + Suspense
  in `App.tsx`; initial JS **250.89 kB → 165.18 kB (gzip 76.19 →
  53.73 kB)** with 12 per-view chunks (1.3–11.7 kB). No new
  dependencies; no heavyweight chart libraries; loading/error
  boundaries on lazy routes.
- CSRF: mutations go through `postWithCsrf`; on a 403 the client
  retries once with a freshly fetched token and adopts a rotated
  `csrf_token` returned in-band by reset/logout.

## 8. Accessibility (axe-verified)

- Semantic landmarks (`nav`, `main`, headings in order), a skip link,
  `aria-current="page"` on the active route, `aria-expanded` on Atlas
  nodes and the sidebar toggle, `aria-selected` on scenario buttons.
- Dialog focus trapping/return and ESC support in `ConfirmDialog`.
- Live regions for completion/error toasts.
- Minimum touch targets via `.55rem` vertical button padding and
  full-width scenario buttons; long issuer URLs and claim labels wrap
  (`overflow-wrap: anywhere` in `.kv` and `.code`).
- Auth errors are calm, accurate reason codes — never raw tokens,
  codes, state, verifiers or session IDs.
- **Axe scan (`e2e/a11y.spec.ts`, @axe-core/playwright):
  ZERO-TOLERANCE (v3 P2-19; v4 P2-22): 25/25 tests, 0 total violations at ANY
  impact level** (minor/moderate included), 2026-11-11 — all 12
  routes, student + officer sign-in, reset dialog, I6 error state,
  Atlas inspector expanded, Live Keycloak namespace, mobile menu
  open at 320 px, reduced motion, loading state, focus order, plus 3
  new v4 scans (Settings identity-unknown, Overview
  error-with-retry, Atlas keyboard traversal). The
  assertion is `expect(violations).toEqual([])`; there are no
  approved exceptions. The v3 contract found and fixed 4 real
  violations: `scrollable-region-focusable` (all 7 `.table-wrap`
  divs now `tabIndex={0} role="region"` with a real label);
  `label-content-name-mismatch` (Findings sort buttons' `aria-label`
  now contains the visible text + arrow); `label-content-name-mismatch`
  (menu button `aria-label` "Close navigation menu" didn't contain
  visible text "Close menu" — aria-label removed, visible text is
  the name); `aria-prohibited-attr` (Overview loading skeleton
  `<div aria-label>` without a role → `role="status"`).
  The v2 contract (fail only on serious/critical, 6/6 views) is
  superseded. The first v2 run found 6 violations and all were fixed
  in the shipped CSS/TSX: listbox `aria-required-children`
  (Scenario Studio `<ul>/<li>` → `<div>` + direct `role="option"`
  buttons); `role="listitem"` on a `<button>` and `aria-pressed` on
  `role="tab"` (Flow Inspector — role moved to the wrapper `<div>`,
  tabs became plain toggle buttons); heading order (Atlas node
  `<h3>` → `<span class="atlas-title">`); `.faint` contrast
  (`#7E8898` → `#98A3B5`); `.atlas-node.notrun` opacity removed (kept
  dashed border + NOT RUN badge); prose links underlined (`p a, li a,
  td a, .breadcrumbs a` — a later same-specificity rule had silently
  removed the underline from breadcrumbs).

## 9. Screenshots (`e2e/screenshots.spec.ts`, `npm run test:screenshots`)

**99 PNGs in `frontend/e2e/screenshots/`, all fresh v4**, captured
2026-11-11 against the live host-run stack (real Keycloak 26.8.2 +
v4 backend + Vite preview): all 12 views at 320×740, 390×844,
768×1024, 1280×800, 1440×900 and 1920×1080, plus 12 state shots
(logged-out / login-success / access-denied / empty / loading /
error / confirmation, 200%/400% zoom-layout equivalents, 125% text
size, forced colours) and 3 labelled state shots
(`state-overview-provider-down`, `state-overview-not-run`,
`state-settings-identity-unknown`). Every shot carries the programmatic overflow
assertion (`scrollWidth <= innerWidth`) — all passed.

**Screenshot determinism contract (v4, P2-18):** `waitSettled()`
(`screenshots.spec.ts:86`) — networkidle, then a settled marker
(`data-testid`, e.g. `overview-settled`, `src/pages/Overview.tsx:78`)
or an honest error alert, then zero `.skeleton` elements; a timeout
FAILS the test instead of screenshotting a loading state. Loading
cards carry human labels ("Measuring lab status…", "Waiting for the
lab…") with `aria-live="polite"`; error states have retry buttons.
State shots are separate labelled files
(`state-*-loading|empty|error|provider-down|not-run.png`), never a
loading skeleton presented as a measured shot. All 99 PNGs were
inspected: 9 top-crop sheets (top 1000 px of every shot, 3 per row)
+ 13 full-width key crops. Checked per shot: no blank placeholder
cards in normal shots, no "No measured status yet" in a shot
claiming measured data, no horizontal overflow at any width, Atlas
states + reason codes legible, Settings reset card populated.
**Result: P2-18 defect FIXED** — the 390×844 Overview now shows
measured tiles (OK, Reachable, officer_01, 20 logins, 18 scenarios).
Three inspection defects found and fixed in v4: (1) the first
not-run shot only emptied the live-login list, so it still showed a
previous test's `student_01` as last verified login — the test now
also overrides `lab/status` with `last_verified_login: null` and
asserts the tile itself reads NOT RUN and the count tile reads 0;
(2) the first settings shot caught the page mid-load ("Loading
configuration…" with the status card missing) because v4's identity
check resolves independently of config/status — the test now also
waits for "Measured lab status"; (3) reason code wrapped mid-word
(`WRONG_AUDIENCE` → `WRONG_AUDIEN CE`) — fixed with `<wbr/>` after
each underscore (see §6). One remaining cosmetic note, NOT fixed:
the Validation Rules / Findings tables at 320–390 px scroll
horizontally inside `.table-wrap` (by design; the page itself does
not overflow). The v3 set (97 PNGs) is superseded.

Two real defects were found in the screenshots and fixed (both in
`src/styles.css`): `.code` `word-break: break-all` splitting words
mid-syllable, and the Findings `WRONG_AUDIENCE` chip wrapping
mid-word (fixed with `.table-wrap table{min-width:880px}` +
`.table-wrap .code{white-space:nowrap}`; re-captured and verified).

Known capture artifacts, **not UI bugs** (proven with viewport-only
shots kept in `e2e/screenshots/`): on long pages at 320 px,
`fullPage` stitching duplicates the sticky top bar mid-page and
leaves a blank band at the top
(`320x740-scenario-result.png`, `320x740-modal-reset.png`,
`1440x900-modal-reset.png` — in the modal case the dialog sits
mid-page over the reset card in the stitch; in a real browser it is
viewport-centred). The viewport proof
(`320x740-nav-drawer-viewport-proof.png`) shows the drawer as a
correct 276 px full-height scrollable panel. **Forced-colours
limitation:** the headless shell did not visibly restyle the page,
so forced-colours shots are not claimed as high-contrast proof;
axe contrast ratios still pass.

## 10. What is deliberately NOT in the system

- No light theme (the dark system is the whole product; a second
  theme done badly would be worse than none).
- No third-party fonts, analytics, telemetry, or externally hosted
  assets — system font stacks only, fully local.
- No icon font or externally hosted image assets; the brand mark,
  nav glyphs, and Portal crest are inline SVG / CSS.
- No invented charts: the Overview shows executed-run counts by
  status/scenario from recorded results only.

## 11. Atelier v3 (2026-11-11) — what changed from v2

- **Deeper surface layering:** hero hairline grid, metric top-rule
  + brass hover, card shadow; more nuanced spacing/typography.
- **Status:** one readiness pill + expandable diagnostics (was a
  multi-badge wall); 320 px gets one compact priority status row.
- **Navigation:** 12 custom inline-SVG glyphs; `aria-controls`
  corrected to `sidebar-nav` (P2-18).
- **Content truth (P2-21):** Overview no longer says "Nothing here
  talks to a real identity provider" — the correct truth is that no
  real-world accounts or production IdPs are involved, but the lab
  DOES use genuine local Keycloak software (real codes, real PKCE,
  real signed ID tokens). All 12 views swept for mocked-implying
  labels; none others found.
- **Reviewer path + portfolio summary (P2-23):** 8-step guided
  5–10 minute path on Overview and in Reports; privacy-safe
  portfolio evidence summary export with AI-assisted authorship
  disclosed.
- **Performance (P2-24):** route-level lazy loading; initial JS
  250.89 kB → 165.18 kB (gzip 76.19 → 53.73 kB).
- **Accessibility (P2-19):** axe contract raised from
  serious/critical-only (6 views) to zero-tolerance at any impact
  on 22 tests covering all 12 routes and states; 4 real violations
  fixed (see §8).
- **Screenshots:** 50 PNGs at 5 viewports → **97 PNGs at 6 widths**,
  all fresh v3, with programmatic overflow assertions and a
  settings-shot wait for operator identity (see §9).

## 12. Atelier v4 (2026-11-11) — what changed from v3

- **ModeBadge corrected (P2-23):** the v3 mapping was backwards
  (real → azure, fixture → teal). Now teal (`badge-live`) is ONLY
  for a real Keycloak-verified identity; azure (`badge-fixture`)
  is for offline fixture / protocol data (`Badge.tsx:21`,
  `styles.css:106-113`); `RunStatusRow` no longer hardcodes
  `badge-fixture` — it uses `ModeBadge`. See §7.
- **Identity Transaction Atlas (P2-20):** 7 stages (was 6), the v4
  state vocabulary (VERIFIED / DENIED / ERROR / NOT REACHED /
  FIXTURE-ONLY / NOT OBSERVED / NOT RUN) with the pill mapping in
  §6, data from recorded events only, inspector with Recorded at /
  Provenance / "Flawed fixture omitted check", horizontal ≥1024 px
  and vertical below, full text alternative, keyboard navigation,
  `<wbr/>`-after-underscore reason-code wrapping. See §6.
- **Settled screenshots (P2-18):** `waitSettled()` determinism
  contract (see §9); 99 PNGs, all fresh v4, all inspected; the
  390×844 Overview now shows measured tiles. Three inspection
  defects found and fixed (see §9).
- **Settings error truthfulness (P2-23):** `meState` distinguishes
  checking / signed-in / signed-out / forbidden / unreachable /
  server-error; reset enabled only on a measured officer identity;
  "Retry identity check" button. See §7.
- **Polish (P2-19 / P2-21):** compact top status strip (topbar
  padding sp-3 → sp-2); banner shortened to "Local lab only ·
  loopback 127.0.0.1 · synthetic data only" (the full SYNTHETIC
  notice stays in the brand-sub); Portal page-sub dropped the
  all-caps SYNTHETIC repeat; Overview hero trimmed. Colour
  semantics unchanged: teal only for verified identity, azure for
  protocol/fixture data, brass for selection, amber caution, red
  denial/failure. All 12 routes unchanged.
- **Accessibility (P2-22):** axe zero-tolerance **25/25, 0
  violations** (was 22/22); 6 widths + 200%/400% zoom + 125% text
  size + forced-colours; no horizontal overflow (asserted per
  shot); `prefers-reduced-motion` respected; no heavy libraries.
- **Playwright workers (P1-09):** `playwright.config.ts:17`
  `workers: 1` default with `PLAYWRIGHT_WORKERS` env override
  (8 GB target); `--list` confirms 57 tests in 4 files.
- **Performance:** initial JS 165.18 kB → **165.14 kB**
  (gzip 53.73 → 53.71 kB), 14 JS assets (index + 13 lazy chunks;
  the extra chunk is the `Badge` module split). No new
  dependencies.

## 13. Atelier v7 (2026-11-11) — refinements only, no theme change

Same v6 tokens (ink/graphite/porcelain/brass/teal, Georgia display /
system-sans body / monospace technical), same 12 routes, no new
dependencies. Every change below is presentational: spacing, density,
chips, legends, and wording. No logic moved: the stale state machine
lives in `useResource` (v6) and the step states live in the pages'
existing data; WS2 owns the logic in `api.ts`, `useResource.ts` and
`liveLogins.ts`.

- **Overview Data requests, denser (a):** on ≥1024 px the four
  request states sit two-across (`.resource-states .kv` becomes a
  4-column grid, dt/dd pairs kept together by auto-flow); narrow
  screens keep the single-column list. The card is now
  `aria-live="polite"` so a state change is announced. Same four
  rows, same pills, same timestamps — nothing hidden by the density.
- **Stale vs current (b, IF-V6-03):** a step whose evidence comes
  from a fetched resource and whose fetch is STALE shows an amber
  past-tense chip (`.stale-chip`): "Last verified at \<time of last
  successful load\>" — and NO current-green Verified pill anywhere
  in the reviewer path. The "Last verified login" metric tile and
  the live-counts strip carry the same chip. A later successful
  retry returns the step to Verified and the chip disappears. Teal
  is still reserved for current, verified success; amber is
  historical, never current.
- **Provenance legend + degraded export (c):** Findings &
  Evidence opens with a legend of the three download kinds —
  Server-verified artifact (plain note), Client-derived from
  server (blue info notice), LOCAL UNSAVED COPY (dashed amber
  warning, `.export-degraded`, 2 px dashed border) — so a degraded
  export looks intentionally different at a glance and can never be
  mistaken for a server-verified artifact. The Reports evidence-pack
  card points at the same legend.
- **Atlas 7-state legend + missing-stage reasons (d):** the Flow
  Inspector lists all seven node states with their badges
  (VERIFIED / DENIED / ERROR / NOT REACHED / FIXTURE-ONLY /
  NOT OBSERVED / NOT RUN) above the diagram, and the inspector
  panel gains a "Missing-stage reason" row for any non-verified
  stage. Incomplete is never VERIFIED: in a live timeline a missing
  stage was pruned at the retention cap, never reached, or never
  observed by the BFF — the reason is written down, not assumed.
- **Live counts hero (e):** the Overview "Live login counts" strip
  shows the retained transaction total large (`.count-hero`) and
  the retained event total small beneath it (`.count-sub`), with the
  three distinctions in words: transactions vs events, retained vs
  all-time, and the last-20 sample vs the retained total. Unknown
  stays Unknown, never zero.
- **Settings identity state (f):** the identity line carries a pill
  whose tone follows the measured state — teal only for a measured
  officer, amber while the identity is unknown for any reason, red
  only for a refused (403) check — and the reset button is
  `aria-describedby` the identity line, so a screen reader hears
  exactly why it is enabled or disabled. Body scroll locks while a
  reset confirm dialog is open (Settings effect); focus trap,
  Escape and return-focus already lived in `ConfirmDialog` (v6)
  and were verified, not re-implemented.
- **Reports person/environment steps (g):** each walkthrough step
  carries persona/environment chips (`.step-context`: student_01 /
  officer_01 / reviewer × live Keycloak / offline fixture /
  exports). Presentational labels only; the per-person attribution
  logic is WS2's IF-V6-04.
- **Forced colours (new in v7):** `@media (forced-colors: active)`
  gives badges, pills, chips and the stale chip a real
  `ButtonText` border, the focus ring uses system `Highlight`, a
  stopped Atlas node uses a `Mark` border (its colour-only inset
  bar is removed), and metric top borders use `ButtonText` — so
  every state survives without colour. Reduced motion, skip links,
  focus-visible and aria-live behaviour are unchanged from v6.
- **Performance:** initial JS 168.07 kB → **170.04 kB**
  (gzip 54.70 → 55.20 kB), `index-BXc-Ornr.js` (WS3-measured
  `npx vite build`, 2026-11-12 ~00:53 UTC, at the then-current code
  state — the hash will move again when WS2's in-progress logic
  lands; the coordinator re-measures at final code). No new
  dependencies. Axe: **25/25, 0 violations** (coordinator's
  Playwright re-run at final code, 2026-11-12 ~01:12 UTC; v6 was
  25/25, 0 violations). Build at final code: `index-CpvwjTcU.js`
  170.04 kB / 55.20 kB gzip, SHA-256 `78f5536d…` (coordinator,
  run twice, byte-identical).
