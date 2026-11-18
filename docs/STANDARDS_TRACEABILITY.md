# Standards Traceability — IdentityForge

> How to read this file: each row maps one implemented control to the
> standard it comes from, what the lab actually does (and does not do),
> where it lives in code, and which tests prove it. "MUST/SHOULD" wording
> follows the cited source; where the lab adds a stricter choice of its own,
> the row says **lab choice**, not an RFC requirement. IdentityForge
> implements a *deliberate subset* of these standards — it does not claim
> full RFC compliance.

Conventions: **Positive test** = legitimate input still works.
**Negative test** = attack input is rejected *and* no session/resource
access results. Code entry points are package paths under
`backend/src/identityforge/` unless stated otherwise. Exact test names are
owned by the backend agent; this file names the test *intent* so a reviewer
can find it.

## RFC 9700 — OAuth 2.0 Security Best Current Practice

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| Use authorization code flow with PKCE; do not use implicit flow | RFC 9700 §2.1, §4.3 | Implemented. Implicit flow is disabled in the Keycloak client (`implicitFlowEnabled: false`); the backend only implements the code flow | `auth/` (login/callback), Keycloak realm import | I1 happy-path login | I3 wrong verifier; I4 wrong redirect | Lab covers the web-client code flow only; native/mobile flows out of scope |
| Sender-constrain / bind the authorization code to the client | RFC 9700 §2.1, §4.4 | Implemented via PKCE S256 (RFC 7636). **Lab choice:** public client, so PKCE is the binding mechanism; no client secret is used for code binding | `protocol/pkce.py` (naming indicative; see ARCHITECTURE.md) | I1 | I3 | PKCE protects the code only if the verifier stays server-side — it does (BFF) |
| Validate `redirect_uri` exactly; no open redirects | RFC 9700 §4.1.3 | Implemented. Exact string comparison against the single registered URI `http://127.0.0.1:8000/auth/callback`; no prefix matching | `auth/` callback validation, realm import `redirectUris` | I1 | I4 (unregistered, prefix-confusion, look-alike URIs) | Single redirect URI only; no multi-URI support |
| Use `state` to bind authorization request/response; verify and invalidate | RFC 9700 §2.1, §4.7 | Implemented. Random, per-transaction, browser-session-bound, single-use | `auth/` transaction store, `protocol/` state handling | I1 | I2 (altered/missing/stale/swapped state) | State is bound to the backend transaction store, not to a signed browser cookie — acceptable in the BFF model |
| Reject authorization responses with errors; do not proceed on `error` | RFC 9700 §4.1 | Implemented. Callback `error` parameter ends the transaction with a safe reason code, no token exchange | `auth/` callback handler | — (error path is itself the negative) | I8/I15 error/malformed callback handling | Error descriptions from the IdP are not displayed verbatim to users |
| Do not use ID token as access token (and vice versa) | RFC 9700 §2.1; OIDC Core §16 | Implemented. ID token is used only for authentication; resource access uses the server-side session, not the ID token | `auth/` token handling, `api/` portal routes | I1 (member resource via session) | Advanced experiment: token substitution (see SCENARIO_METHOD.md) | The lab does not call a separate resource server with access tokens in v1 |
| TLS / HTTPS for production | RFC 9700 §2.1 | **Not implemented — documented exception.** Local HTTP on loopback only. HTTPS is required for any non-localhost use; see SECURITY.md | `docker-compose.yml` (loopback ports), `docs/VALIDATION_AND_LIMITATIONS.md` | — | — | Lab-only; never deploy as shipped |

## RFC 7636 — PKCE (Proof Key for Code Exchange)

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| `code_challenge_method=S256`; challenge = `BASE64URL(SHA256(verifier))` | RFC 7636 §4.2, §4.3 | Implemented. Verifier is cryptographically random (43–128 chars); challenge computed with SHA-256, never `plain` | `protocol/pkce.py` | I1 | I3 (wrong verifier; downgrade attempt in fixture) | `plain` is never generated or accepted by the lab client |
| Verifier kept confidential; sent only in the token request | RFC 7636 §4.4 | Implemented. Verifier lives server-side in the transaction store; never in URLs, logs, or the browser | `auth/` transaction store, `evidence/` redaction | I1 | I3; log/redaction tests assert no verifier in evidence | — |
| Authorization server rejects a mismatched verifier | RFC 7636 §4.6 | Observed, not re-implemented: Keycloak enforces this. The lab's integration test asserts the denial; the offline fixture models it deterministically | `scenarios/` I3 definition; Keycloak (external component) | I1 | I3 | If Keycloak changed behaviour, only the integration lane would catch it |

## OpenID Connect Core 1.0

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| Authorization code flow; `response_type=code`, `scope=openid` | OIDC Core §3.1 | Implemented | `auth/` login | I1 | — | Only the code flow; hybrid/implicit flows not implemented |
| `nonce` generated by the client and validated in the ID token | OIDC Core §3.1.2.1, §3.1.3.7 | Implemented. Random nonce per transaction, stored server-side, compared to the ID-token `nonce` claim; single-use | `auth/` transaction store, `protocol/` token validation | I1 | I8 (missing/wrong nonce, unsolicited callback) | Nonce replay is prevented by transaction single-use; see I7/I10 |
| ID-token validation: `iss`, `aud`, `exp`, `iat`, signature | OIDC Core §3.1.3.7 | Implemented. `iss` = pinned issuer, `aud` = `campus-club-portal`, `exp`/`iat` with bounded clock skew, signature via issuer JWKS | `protocol/` token validation (`PyJWT` + JWKS) | I1 | I5 (wrong issuer), I6 (wrong audience), I7 (expired), I9 (bad signature/alg) | `auth_time`/`acr` not required by the lab profile; documented as out of scope |
| `sub` identifies the subject; identity = issuer + subject, not email alone | OIDC Core §2, §5.1 | Implemented. Sessions are keyed by `(iss, sub)`; roles resolved from trusted claims via app policy | `auth/` session creation, `security/` policy | I1 (member resource) | I13 (cross-user / role spoofing) | Lab uses Keycloak realm roles; no custom claims mapping beyond roles |
| Discovery from a trusted issuer only | OIDC Core §4; Discovery 1.0 | Implemented. Discovery document fetched only from the pinned issuer; arbitrary discovery URLs rejected | `auth/` provider config | I1 | I18 (external issuer URL rejected) | No dynamic discovery; one pinned issuer |

## RFC 9207 — Authorization Server Issuer Identification

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| Bind the authorization response to the expected issuer (`iss` parameter / issuer identification) | RFC 9207 §2, §3 | Implemented in the lab's sense: the callback is accepted only for the transaction's expected issuer, and the token `iss` must match it. **Note:** RFC 9207's `iss` response parameter is a mix-up defence for multi-issuer clients; the lab has a single pinned issuer, so the control is applied as issuer allowlisting + transaction binding rather than a multi-issuer mix-up test | `auth/` callback + token validation | I1 | I5; advanced experiment: multi-issuer mix-up (see SCENARIO_METHOD.md) | Single-issuer lab; a genuine multi-issuer mix-up test is an optional advanced experiment, not a v1 claim |

## RFC 8725 — JWT Best Current Practices

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| Validate `alg`; never accept `alg=none`; prevent algorithm confusion | RFC 8725 §2.1, §3.6 | Implemented. Allowlist: RS256 only (lab profile). `none`, `HS256`-with-RSA-key, and unknown algorithms rejected | `protocol/` token validation | I1 | I9 (unsigned, wrong-alg, wrong-key, tampered) | Only RS256 keys from the lab issuer are supported; no EC/EdDSA in v1 |
| Verify signature with the key belonging to the issuer; do not trust `jwk`/`jku`/`x5u` headers from the token | RFC 8725 §3.6, §4.1 | Implemented. Keys come only from the pinned issuer's JWKS endpoint; header-embedded key material is ignored | `protocol/` JWKS handling | I1 | I9, I14 (wrong-key, key-discovery errors) | JWKS caching/rotation: keys are re-fetched on unknown `kid` (documented behaviour); rotation behaviour is an advanced experiment |
| Validate `exp` and do not accept tokens without it | RFC 8725 §3.6 | Implemented. `exp` required; expired tokens rejected | `protocol/` token validation | I1 | I7 | Bounded clock skew only (small, documented constant) |
| Reject tokens with unexpected `aud`/`iss` | RFC 8725 §3.6 | Implemented (see OIDC rows above) | `protocol/` token validation | I1 | I5, I6 | — |

## RFC 10017 — OAuth 2.0 for Browser-Based Applications

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| BFF pattern: tokens handled server-side; no tokens in browser storage | RFC 10017 §6 | Implemented. Backend-for-frontend exchanges the code and validates tokens; the browser holds only an opaque session cookie | `auth/`, `api/`, frontend (no token storage) | I1 | I11/I12 (session handling); code review: no `localStorage` token usage | The lab does not implement the token-mediated (non-BFF) browser pattern at all |
| Protect the BFF session (HttpOnly, SameSite, CSRF) | RFC 10017 §6, §7 | Implemented. HttpOnly, `SameSite=Lax`, rotation on login, CSRF checks on mutations | `auth/` session + CSRF, `security/` | I1 | I11, I12, I16 | `Secure` flag only under HTTPS (local HTTP exception, documented) |

## OWASP ASVS / Session Management (guidance, not an RFC)

| Control | Source | Lab scope | Code entry point | Positive test | Negative test | Limits |
|---|---|---|---|---|---|---|
| Session fixation defence: rotate ID on authentication | OWASP ASVS 3.3 / Session Management Cheat Sheet | Implemented | `auth/` session creation | I1 | I11 | — |
| Logout invalidates server-side; no resurrection | OWASP ASVS 3.3 | Implemented | `auth/` logout | I1 → logout → re-check | I12 | — |
| Authorization enforced server-side per resource | OWASP ASVS 4.1 | Implemented | `security/` policy, `api/` portal routes | I1 (member OK, officer denied for student) | I13 | Two roles only (member/officer) |
| CSRF protection on state-changing requests | OWASP ASVS 4.2 | Implemented (synchronizer/origin check as applicable; see API_CONTRACT.md) | `security/` CSRF, `api/` mutations | Legitimate console actions succeed | I16 | — |
| Security headers; no caching of sensitive responses | OWASP ASVS 14 / 3.x | Implemented (headers + `Cache-Control: no-store` on sensitive API/pages; see API_CONTRACT.md) | `api/` middleware | I1 (headers present) | Header-absence regression test | Local HTTP limits some header value (HSTS not meaningful on HTTP) |

## What this file does NOT claim

- **No full RFC compliance claim.** The lab implements the subset above
  for the web code flow with a single pinned issuer. It does not implement
  every RFC 9700 recommendation (for example, DPoP, mTLS, PAR, or
  pushed-authorization requests), and it does not claim to.
- **Keycloak-enforced controls are observed, not owned.** Code single-use,
  exact redirect matching at the authorization server, and PKCE enforcement
  at the token endpoint are Keycloak behaviours. The lab tests that it
  *observes* them; it does not re-implement them.
- **Traceability is a map, not a proof.** Each row names a test; the test
  evidence (run reports) is what proves the control works. See
  `docs/TEST_MATRIX.md` and `example-reports/`.
