# Threat Model — IdentityForge

> Plain-language summary: this lab studies how a web login can go wrong.
> The "attacker" in every scenario is a **controlled, local test input** —
> a tampered token, a swapped state value, a wrong redirect — run against
> the lab's own synthetic services on your own machine. There is no real
> victim, no real account, and no external target.

## 1. System in scope

| Component | Role | Trust |
|---|---|---|
| Browser (reviewer) | Starts login, follows redirects, holds the session cookie | Untrusted input source; cookies can be replayed by anyone who steals one (lab only) |
| Backend BFF (`127.0.0.1:8000`) | Runs the OIDC code exchange, validates tokens, owns sessions, enforces authorization | **Trusted.** All security decisions happen here, never in the browser |
| Keycloak (`127.0.0.1:8080`, realm `identityforge-lab`) | Local identity provider: authenticates synthetic users, issues codes/tokens | Trusted **only** as the pinned, allowlisted issuer. Its keys are fetched from its JWKS endpoint, never from a token header |
| Research console (frontend, `127.0.0.1:5173`) | Displays lab state, runs offline scenarios, shows reports | Untrusted presentation layer; it never makes security decisions |
| Offline scenario harness (pytest/CLI) | Deterministic fixtures + isolated flawed validators | Trusted test code, but its flawed variants are **not** the real app |

All components run on loopback or an isolated Compose network. See
`docs/ARCHITECTURE.md` for the diagram and trust boundary.

## 2. Assets (all synthetic)

- Synthetic identities `student_01` (member) and `officer_01` (member+officer).
- The member-only resource and the officer-only resource (fictional club data).
- Server-side sessions (opaque cookie IDs) and the transaction state
  (state / nonce / PKCE verifier) that binds one login attempt together.
- Lab evidence: redacted run reports. These must never contain tokens,
  codes, verifiers, or cookies.

## 3. Attackers modelled (lab-local only)

| Attacker | Capability | Example scenario |
|---|---|---|
| Curious browser user | Can edit URLs, replay a callback, reuse an old cookie | I2 (stale state), I7/I10 (replay), I12 (stale cookie) |
| Token forger (offline fixture) | Can mint a locally signed JWT with a wrong issuer/audience, expired `exp`, or `alg=none` | I5, I6, I9 |
| Redirect manipulator (offline fixture) | Supplies an unregistered redirect URI / look-alike destination | I4 |
| Code interceptor (offline fixture) | Observes an authorization code and tries to redeem it with a wrong PKCE verifier | I3, I10 |
| Privilege seeker | A signed-in member asks for the officer-only resource, or for another user's resource | I13 |
| Cross-site requester | Tricks a signed-in browser into issuing a state-changing request from another origin | I16 (CSRF) |
| Input abuser | Sends overlong, malformed, or log-injection content to parsers | I17 |
| Configuration abuser | Supplies an external issuer/JWKS URL to make the backend fetch attacker-controlled key material | I18 (SSRF) |

**Not modelled:** attacks on real identity providers, real users, network
infrastructure, the reviewer's host OS, or Keycloak itself as a product.
Keycloak is treated as a trusted component in the lab; vulnerabilities in
Keycloak upstream are out of scope and should be reported upstream.

## 4. Threats and controls

| # | Threat | Control (where) | Scenario |
|---|---|---|---|
| T1 | Login CSRF / transaction confusion: an attacker starts a login and the victim's browser completes it | Random per-transaction `state`, bound to the browser session, verified once then invalidated | I2, I8, I15 |
| T2 | Authorization-code interception / theft | PKCE S256: code is useless without the random verifier; verifier never leaves the backend | I3 |
| T3 | Code sent to an attacker's site | Exact registered redirect URI only; no prefix/look-alike matching | I4 |
| T4 | Token from a different issuer accepted | Issuer allowlist: `iss` must equal the pinned lab issuer exactly; discovery only from that issuer | I5, I18 |
| T5 | Token meant for another app accepted | Audience must equal `campus-club-portal` exactly | I6 |
| T6 | Forged / tampered / unsigned token accepted | Signature verified against the issuer's JWKS; `alg` allowlist (RS256 only in the lab); `alg=none` rejected | I9, I14 |
| T7 | Expired or replayed token/transaction accepted | `exp`/`iat` checked with bounded clock skew; codes and state are single-use; nonce validated | I7, I8, I10 |
| T8 | Session fixation / session reuse after logout | Session ID rotated on login; logout revokes server-side; old cookie rejected | I11, I12 |
| T9 | Signed-in user reaches a resource they may not use | Independent server-side authorization: role + subject checked per resource, not implied by a valid token | I1, I13 |
| T10 | Cross-site mutation on behalf of a signed-in user | CSRF token / origin check on state-changing endpoints; `SameSite=Lax` cookies | I16 |
| T11 | Parser crash / log injection / oversized input | Bounded input sizes, strict schemas, structured logging with redaction, no raw user input in logs | I17 |
| T12 | Backend tricked into fetching attacker keys (SSRF) | Issuer/JWKS URLs come only from pinned lab config; user-supplied URLs rejected | I18 |
| T13 | Flawed fixture leaks into the real portal | Flawed validators are pure functions in the offline harness; no endpoint, toggle, or env var selects them in the running app | All; see §5 |
| T14 | Sensitive data leaks via evidence/reports | Redaction at the evidence layer: hashes only, no tokens/codes/verifiers/cookies/passwords | All; see `docs/VALIDATION_AND_LIMITATIONS.md` |

## 5. The flawed-fixture boundary (the most important design rule)

Each negative scenario has **two** measurements:

1. **Secure variant** — the real validator (the same code the portal uses).
   Expected: reject, no session, no resource access.
2. **Flawed variant** — a deliberately weakened copy of one check, run only
   inside the offline pytest/CLI harness on synthetic transactions.

The flawed variant is **not** a mode of the application. It is not reachable
from the browser, not selectable in the UI, not enabled by an environment
variable, and not served by any endpoint. Its only purpose is to prove the
guard matters: the same attack input that the secure variant rejects is
accepted by the flawed variant, which is exactly the before/after evidence
the research question asks for. See `docs/SCENARIO_METHOD.md`.

## 6. Residual risks (honest limits)

- **Local HTTP.** The lab runs over plain HTTP on loopback. On any other
  network, cookies and codes would be observable. This is a labelled
  development exception, not a deployment model.
- **Keycloak as a black box.** The lab relies on Keycloak to enforce code
  single-use and exact redirect matching. Tests observe that behaviour
  rather than re-implementing it; if Keycloak's behaviour changed, the
  lab's integration tests (not the unit tests) would catch it.
- **Clock skew.** Token time checks allow a small bounded skew; a badly
  skewed reviewer clock can cause false rejections. `doctor.sh` does not
  check the clock — if logins fail with expiry errors, check the system clock.
- **Synthetic credentials.** The realm import contains lab-only passwords.
  Anyone with the archive can sign in as the synthetic users — that is
  by design for a lab, and why the lab must stay on loopback.
- **Keycloak 26.8.2 pin.** The 26.8 line is the actively supported
  Keycloak line as of this release (26.8.2 released 2026-11-05). The pin
  is verified to exist and boot, but reviewers should check for a newer
  26.8.x patch before any use beyond this lab.

## 7. Out of scope (explicitly not tested)

Real-world phishing, social engineering, Keycloak CVEs, TLS deployment,
production federation, SAML, mobile flows, and attacks against any system
outside this lab. See `docs/VALIDATION_AND_LIMITATIONS.md` for the full list.
