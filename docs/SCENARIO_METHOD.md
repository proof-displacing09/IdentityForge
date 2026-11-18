# Scenario Method — IdentityForge

> Plain-language summary: a scenario is a small, honest experiment. You
> change exactly **one** thing about a login, watch what the lab does, and
> write down what happened — what the secure version did, and what a
> deliberately weakened version did with the same input. One change at a
> time, or you cannot tell which change caused the result.

## 1. What a scenario is

Every scenario has:

| Field | Meaning |
|---|---|
| `scenario_id` / title | e.g. `I6_wrong_audience` |
| Explanation | What the control is and why it matters, in plain language |
| Attack surface | Which step of the login the input touches |
| Attacker-controlled input | The exact deviation, in the lab only |
| Expected secure result | What the secure validator *should* do |
| Actual observed result | What it *did* do, measured (never assumed) |
| Violated security rule | The standard/control that would be broken if it were accepted |
| Flawed fixture result | What the isolated weakened variant did with the same input |
| Decision step | The exact transaction step and predicate that accepted/rejected |
| Proof artifacts | Redacted event IDs, report file, run ID, hashes |
| Mode | `REAL KEYCLOAK` / `DETERMINISTIC OFFLINE FIXTURE` / `PREVIOUS SAVED EVIDENCE` / `NOT RUN` |

The report schema is defined in `docs/API_CONTRACT.md` and
`example-reports/REPORT_TEMPLATE.json`.

## 2. The two-variant rule (secure vs flawed)

For every negative scenario the lab measures **two** outcomes on the
**same** attack input:

1. **Secure variant** — the real validator (the code the portal uses).
2. **Flawed variant** — a copy of that validator with exactly one check
   removed or weakened, running only inside the offline pytest/CLI harness.

The flawed variant is a *teaching instrument*, not a product mode:

- It lives only as dependency-injected functions in the offline harness.
- It is never an HTTP endpoint, never a UI toggle, never an environment
  variable, and never connected to the real session store.
- A "flawed fixture allowed it" result is **not** a real exploit. It is
  evidence that the removed check is the thing doing the work — the
  before/after comparison the research question asks for.

If Keycloak itself enforces the control (for example, PKCE at the token
endpoint, code single-use), the flawed variant may be inapplicable to the
real IdP. In that case the report says so explicitly instead of inventing a
flawed Keycloak.

## 3. One deviation per negative test

Each negative fixture injects **precisely one** controlled deviation. If a
test needs two deviations, it is two tests. This is what makes the result
interpretable: a rejection can be attributed to the one changed check.

## 4. The core scenarios (I1–I7)

| ID | Title | Attacker-controlled input | Expected secure result | Flawed variant |
|---|---|---|---|---|
| I1 | Normal login (positive baseline) | Known test identity, correct client, registered callback, valid transaction, correct PKCE, valid signed ID token | Session created; member resource accessible; officer-only action denied for a normal student | — (baseline; the flawed variants are measured against it) |
| I2 | Incorrect state / login transaction binding | Altered, missing, stale, or unrelated `state`; optionally a swapped browser transaction in the isolated fixture | Callback rejected, no session | Skips the state check |
| I3 | Wrong PKCE verifier | S256 challenge bound to one verifier; token request with a different verifier (or downgrade attempt in the fixture) | Token endpoint denies the exchange; no token/session | Accepts any verifier |
| I4 | Invalid redirect URI | Unregistered/mismatched redirect, prefix confusion, extra path/query, look-alike destination (fixture names only) | Authorization server rejects the unregistered redirect; no code sent to the alternate target | Accepts any redirect |
| I5 | Wrong issuer | Locally signed fixture ID token whose `iss` is not the allowlisted issuer (two synthetic issuers only, isolated tests) | Rejected despite a well-formed token/signature | Skips issuer check |
| I6 | Wrong audience | Correctly signed fixture token targeting another synthetic client | Rejected despite a valid signature | Skips audience check |
| I7 | Expired or replayed transaction | Expired ID token; previously consumed code/state; repeated callback — as **separate subtests**, not one bundled failure | Rejected according to the relevant boundary; no renewed session from the replay | Skips expiry / single-use check as applicable |

## 5. Additional scenarios (I8–I18)

| ID | Title | Expected secure result |
|---|---|---|
| I8 | Missing/wrong OIDC nonce / unsolicited callback | Rejected with `NONCE_MISMATCH` (or state rejection for an unsolicited callback); no session |
| I9 | Unsigned, wrong-algorithm, wrong-key, or tampered token | Rejected (`BAD_SIGNATURE` / `ALG_NOT_ALLOWED`); no session |
| I10 | Code replay / concurrent double redemption | At most one successful redemption; the other denied (`CODE_REUSED`) |
| I11 | Session fixation / session-identity rotation | Fresh session ID on login; pre-login ID invalidated |
| I12 | Logout and stale session cookie reuse | Old cookie rejected after logout |
| I13 | Cross-user, member-vs-officer authorization boundary | Member denied officer resource; no cross-user access |
| I14 | Missing/malformed tokens and key-discovery errors | Safe rejection, no session, no stack trace |
| I15 | Callback parameter confusion (duplicates, wrong client context) | Safe rejection with a stable reason code |
| I16 | CSRF on sensitive portal operations | Cross-site mutation denied; legitimate mutation succeeds |
| I17 | Overlong inputs, unexpected content types, log injection, malformed JWT/JWK | Rejected or neutralised; parsers do not crash; logs stay clean |
| I18 | Config/SSRF: external URL cannot cause issuer/JWKS retrieval | Rejected (`UNTRUSTED_ISSUER_URL`; metadata / private-IP URLs → `SSRF_BLOCKED`); no outbound fetch |

## 6. Optional advanced experiments

Only when fully justified and correctly implemented:

- Multi-issuer login mix-up with RFC 9207 issuer binding.
- JWKS key rotation and revocation/error behaviour.
- Concurrent sign-in tabs and session-binding edge cases.
- Token substitution (ID token vs access token), subject consistency.
- Privacy-preserving correlation across multiple transaction attempts.
- Bounded property-based/fuzz testing of parser and validator failures.

Each advanced experiment gets the same two-variant treatment and the same
report fields as I1–I7, or it is not reported as an experiment.

## 9. v2 state semantics — what actually happened in each run (P0-06)

The `ComparisonResult` fields `secure_session_created`,
`flawed_session_created`, `session_preexisted`, `session_revoked`,
`flawed_model_status`, `flawed_guard_omitted`,
`flawed_observed_result`, and `protected_resource_disclosed` describe
what the test EXECUTED — never a convenient boolean. A session is only
reported as created when `SessionStore.create/rotate` actually ran
inside that test. The table below is the exact per-scenario contract
(verified against `backend/src/identityforge/scenarios/engine.py`,
2026-11-11). `flawed_model_status` is `EXECUTED` for all 18 scenarios
today: `NOT_MODELED` exists in the schema for a future scenario with no
meaningful flawed path, and no scenario currently claims it. I14 is the
case the directive anticipated as `NOT_MODELED` — instead its flawed
path was executed and PROVEN to reject (a malformed token cannot be
validated even with the signature check omitted), which is the
stronger, honest result.

| ID | Preconditions | Secure expected → observed | Flawed: omitted check → observed result | Session truth |
|---|---|---|---|---|
| I1 | Valid signed token, correct iss/aud/nonce | Session created; member allowed, officer denied | none (valid login) → session created by both paths | `secure_session_created=true`, `flawed_session_created=true` |
| I2 | Transaction exists; attacker presents a different `state` | Rejected `STATE_MISMATCH`; original transaction NOT consumed | `state` → attacker state accepted; session minted by flawed path | both `false` secure; flawed `true` |
| I3 | S256 challenge bound to one verifier; wrong verifier presented | Rejected `PKCE_MISMATCH` at the exchange | `pkce` → wrong verifier accepted; session minted by flawed path | secure `false`; flawed `true`. Live K2: real Keycloak also rejects (400 `invalid_grant`) AND burns the code |
| I4 | Unregistered redirect `…/callback/evil` | Rejected `REDIRECT_URI_MISMATCH`; no code to the alternate target | `redirect_uri` → unregistered redirect accepted; session minted by flawed path | secure `false`; flawed `true`. Live K3: real Keycloak rejects before issuing a code |
| I5 | Token signed correctly but `iss` is a foreign issuer | Rejected `WRONG_ISSUER` despite valid signature | `issuer` → foreign issuer accepted; session minted by flawed path | secure `false`; flawed `true` |
| I6 | Token signed correctly but `aud` is another client | Rejected `WRONG_AUDIENCE` despite valid signature | `audience` → wrong audience accepted; session minted by flawed path | secure `false`; flawed `true` |
| I7 | Expired token (−300s, beyond 120s skew) AND a one-use state replayed — two SEPARATE assertions | Expired → rejected `EXPIRED`; first state use ok, second rejected `STATE_REUSED` | `expiry` → expired token accepted; session minted by flawed path | secure `false`; flawed `true` |
| I8 | Token with a different `nonce` | Rejected `NONCE_MISMATCH` | `nonce` → wrong nonce accepted; session minted by flawed path | secure `false`; flawed `true` |
| I9 | Tampered signature (alg-none and wrong-key covered by unit tests) | Rejected `BAD_SIGNATURE` | `signature` → tampered token accepted; session minted by flawed path | secure `false`; flawed `true` |
| I10 | First redemption already created a legitimate session; same code presented again | First redemption ok; second rejected `CODE_REUSED` | `code_single_use` → second redemption minted another session | `session_preexisted=true`, `secure_session_created=false` (the session belongs to the FIRST redemption, not the replay); flawed `true` |
| I11 | Attacker knows a pre-login session id | Rotated to a fresh id; known id revoked | `session_rotation` → attacker-known id stays valid after login (no rotation); nothing new created | `secure_session_created=true` (rotation), `session_preexisted=true`, flawed `false` (the old session SURVIVES — the harm is survival, not creation) |
| I12 | Logged in, then logout | Stale cookie rejected `SESSION_REVOKED`; member resource denied after logout | `logout_revocation` → stale id stays valid after logout; nothing new created | `session_preexisted=true`, `session_revoked=true`, flawed `false` (old session survives) |
| I13 | Student logged in; officer resource requested | Member allowed; officer denied `POLICY_DENIED` | `server_side_policy` → officer resource disclosed via spoofed token role claim | `session_preexisted=true` (the student session stays valid — the denial is about the RESOURCE, not the session); flawed `false`, `protected_resource_disclosed=true` |
| I14 | Token is `not.a.jwt` (unparseable) | Rejected `MALFORMED_TOKEN` | `signature` → flawed path ALSO rejects: a malformed token cannot be validated even without the signature check (proven, not assumed) | both `false` |
| I15 | Callback with duplicate `state` parameters | Rejected `CALLBACK_MALFORMED` | `callback_param_uniqueness` → first of two duplicate states accepted; login proceeds to session creation | secure `false`; flawed `true` |
| I16 | CSRF on a mutation (logout/reset), NOT a login | Positive control (matching header + cookie + trusted Origin) OK; 6 single-factor negatives (wrong header, missing cookie, missing header, hostile Origin, hostile Referer, rotated/stale token) each `CSRF_DENIED` | `csrf` → cross-site mutation allowed without a valid token | No session concept here: both `false`. `flawed_observed_result` says so explicitly |
| I17 | 10,000-char input; log line with an injected newline | Overlong input rejected `INPUT_TOO_LONG`; CR/LF stripped from logs | `input_length/log_sanitize` → overlong input accepted; raw value logged (log injection) | No session concept here: both `false` |
| I18 | Issuer/JWKS URLs pointing at `169.254.169.254` and `evil.example` | Rejected (`SSRF_BLOCKED` / `UNTRUSTED_ISSUER_URL`); no outbound fetch | `issuer_url_allowlist/jwks_url_allowlist` → external URL accepted for fetch | No session concept here: both `false` |

Reading rules that follow from the table:

- A rejection does NOT imply "no session existed": I10/I13 deny an
  action while a legitimate session remains valid. The UI says so.
- A flawed "allowed" does NOT imply "a session was created": I11/I12
  flawed paths let an OLD session survive; I16/I17/I18 have no session
  at all. The harm is named in `flawed_observed_result`.
- `flawed_observed_result` is the single source of truth for what the
  flawed path observably did; `flawed_result` alone (`allowed` /
  `rejected`) is not enough to interpret a scenario.

## 10. How to run a scenario

Offline (no Docker, no Keycloak — the honest core):

```bash
cd backend
python -m identityforge.cli scenario I6
python -m identityforge.cli verify-all
```

Real Keycloak (reviewer machine with Docker; lab running):

```bash
./scripts/start.sh
# then run the integration lane — see docs/TEST_MATRIX.md §3
./scripts/test-all.sh --with-keycloak
```

The UI (Research Console → Scenario Studio) is an orchestration and
presentation layer over the same measured results. It never invents an
outcome: a scenario card shows the stored expected/observed fields, the
mode, and the report link. A scenario that has not run shows `NOT RUN`.

## 11. Reading a secure-vs-flawed comparison without exaggeration

- **"Flawed fixture allowed" ≠ "account takeover."** It means one weakened
  check accepted one synthetic input in an isolated harness. It proves the
  check matters; it does not prove a real attacker could exploit the real
  portal.
- **"Secure fixture denied" ≠ "the system is fully safe."** It means this
  input, at this step, was rejected. Other inputs, other steps, and the
  real IdP still need their own evidence.
- **A JWT being invalid is not a full attack.** A failed login is not proof
  of complete safety. Define success and failure by the asserted
  observations (reason code + no session + no resource access), and say so
  in the report.
- **Distinguish four different facts** in every report: the input was
  accepted by a handler; the validator's decision; whether a session was
  minted; whether a protected resource was actually accessed.
