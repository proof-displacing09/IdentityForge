# Security Policy — IdentityForge

> **IdentityForge is a localhost-only educational laboratory.** It is not a
> production identity system, not a penetration-testing tool, and not
> suitable for remote deployment as shipped. Local HTTP is an explicitly
> labelled development exception; see `docs/VALIDATION_AND_LIMITATIONS.md`.

## Scope

In scope for this policy:

- The IdentityForge lab application in this repository (backend BFF, research
  console frontend, scenario engine, Keycloak realm import, Compose setup).
- The synthetic realm `identityforge-lab`, client `campus-club-portal`, and
  the synthetic test accounts `student_01` and `officer_01`.

Out of scope:

- Any real identity provider (Google, Microsoft, GitHub, a university IdP,
  a bank, or any employer system). IdentityForge never connects to them.
- Any real user account, credential, or personal data. All lab data is
  synthetic and labelled `SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION`.
- Any deployment of this lab on a public network, or use of its intentionally
  flawed offline fixtures against a real system. The flawed variants are
  isolated deterministic test functions, not network services.

## Safety rules built into the lab

1. **Loopback only.** Compose publishes ports only on `127.0.0.1`
   (backend 8000, frontend 5173, Keycloak 8080). No `0.0.0.0` bindings.
2. **No real credentials.** Test passwords exist only in the local realm
   import, are synthetic, and must never be reused anywhere else. Rotate
   them if you share the lab.
3. **Flawed variants are offline-only.** Intentionally weak validators exist
   only as dependency-injected functions inside the offline pytest/CLI
   harness. They are not HTTP endpoints, not selectable in the portal, and
   not toggleable by any environment variable in the running app. They can
   never mint a real portal session.
4. **No tokens in the browser.** ID/access tokens are exchanged and validated
   server-side only. Sessions are opaque random HttpOnly cookies; no token
   is stored in `localStorage` or `sessionStorage`.
5. **Fail closed.** Missing state, wrong issuer/audience, bad signature,
   expired token, reused code, or any validation exception denies the login
   and creates no session. There are no permissive fallbacks.
6. **No SSRF / open redirect.** The scenario runner only addresses
   allowlisted localhost lab endpoints. Issuer and JWKS URLs come from the
   pinned lab configuration, never from user-supplied URLs.
7. **Redaction.** Logs, traces, reports, and screenshots must never contain
   full tokens, authorization codes, PKCE verifiers, client secrets,
   session cookies, or passwords. Evidence stores hashes, not secrets.
8. **CSRF lifecycle (v2).** Mutations (`POST /api/v1/runs`,
   `POST /api/v1/lab/reset`, `POST /auth/logout`) require the
   `x-csrf-token` header to equal the `identityforge_csrf` cookie plus
   a matching `Origin`. Config reads never rotate the token; reset and
   logout rotate it and return the fresh value in-band. See
   `docs/API_CONTRACT.md` §7.
9. **Reset is officer-gated (v3).** `POST /api/v1/lab/reset`
   requires a logged-in officer session plus a valid CSRF token plus
   the confirmation body `{"confirm": "RESET_LAB"}`; a CSRF token
   alone can no longer authorize a reset. A successful reset revokes
   the operator's own session. The v2 "unprivileged on loopback"
   description is withdrawn. Reset cannot touch the Keycloak realm
   or volume — and exactly why the lab must stay on a private
   machine: any officer session on the machine can reset synthetic
   lab state.

## Reporting a vulnerability

If you find a security problem in the lab itself (for example, a way for a
flawed fixture to affect a real session, a token leak in a report, or an
endpoint that accepts an external issuer URL), please report it responsibly:

- Do **not** open a public issue with exploit details, and do **not** test
  the finding against any system other than your own localhost lab.
- Describe the affected file/endpoint, the steps to reproduce locally, and
  the observed vs expected behaviour.
- Include the IdentityForge version/date and whether Docker/Keycloak or the
  offline fixture mode was in use.

Because this is an educational project maintained by its authors, there is
no paid bug bounty and no guaranteed response time. Reports that follow the
rules above will be treated as contributions to the lab's
`docs/SECURITY_ASSESSMENT.md` findings log.

## Supported versions

Only the current release in this repository is supported. Older snapshots
may contain known limitations documented in
`docs/VALIDATION_AND_LIMITATIONS.md`; upgrade by re-extracting the latest
release archive and running `./scripts/reset.sh --confirm` (synthetic data
only — see `scripts/reset.sh` before running it).

## HTTPS

The lab runs over plain HTTP on loopback only. Any deployment beyond
localhost **must** terminate TLS, set `Secure` cookies, re-check the
`SameSite`/`Secure` cookie flags, and re-validate the issuer and redirect
URIs for the HTTPS origin. The lab does not claim to be production-ready,
and this policy does not authorise treating it as such.
