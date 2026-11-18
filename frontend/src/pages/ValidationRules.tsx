/** Validation Rules — grounded in the secure validator
 *  (backend/src/identityforge/protocol/validators.py, pkce.py, jwks.py,
 *  security/csrf.py, security/session.py, security/policy.py).
 *
 *  Columns are stated honestly:
 *  - Implemented: the check exists in the secure validator.
 *  - Negative scenario: the I-scenario that must reject the bad input
 *    (— means no dedicated UI scenario; the check is covered by the
 *    backend unit/protocol test suite instead).
 *  - Evidence: where a reviewer can see the check actually run. */
const RULES = [
  { name: 'State binding', what: 'A random, single-use, browser-session-bound state value is generated per transaction and verified once at the callback.', why: 'Stops cross-site request forgery and transaction swapping on login.', fail: 'Missing, altered or reused state → callback rejected, no session.', scenarios: 'I2, I7', evidence: 'Scenario Studio + Atlas CALLBACK_RECEIVED node' },
  { name: 'PKCE S256', what: 'A random verifier is hashed (SHA-256) into a challenge sent at authorization time; the verifier is presented only at token exchange.', why: 'Stops an attacker who intercepts the authorization code from redeeming it without the verifier.', fail: 'Wrong verifier → token endpoint denies the exchange.', scenarios: 'I3', evidence: 'Scenario Studio + live-gate K2 (real Keycloak)' },
  { name: 'Redirect URI exactness', what: 'The redirect URI must exactly match a registered URI — no prefix tricks, extra paths or look-alike hosts.', why: 'Stops authorization codes being sent to an attacker-controlled destination.', fail: 'Unregistered redirect → authorization server rejects it before any code is issued.', scenarios: 'I4', evidence: 'Scenario Studio + live-gate K3 (real Keycloak)' },
  { name: 'Signature & algorithm', what: 'Signature verified against the issuer JWKS, allowed algorithms only (RS256). alg=none, HS256 and algorithm confusion are refused.', why: 'Stops forged or unsigned tokens.', fail: 'Unsigned, wrong-key or tampered token → rejected.', scenarios: 'I9, I14', evidence: 'Scenario Studio' },
  { name: 'Key ID (kid)', what: 'The token header kid must resolve to a key in the trusted JWKS — never from a token-supplied URL.', why: 'Stops a token pointing at an attacker-controlled key.', fail: 'Unknown or missing kid → rejected (UNKNOWN_KEY).', scenarios: 'I9, I14', evidence: 'Scenario Studio' },
  { name: 'Issuer (iss)', what: 'The ID token issuer must exactly equal the allowlisted local issuer; discovery URLs are pinned, never taken from user input.', why: 'Stops tokens minted by a different (attacker-controlled) issuer being accepted.', fail: 'Wrong issuer → rejected despite a valid signature.', scenarios: 'I5, I18', evidence: 'Scenario Studio + doctor.sh issuer check' },
  { name: 'Audience (aud)', what: 'The ID token audience must be this client (campus-club-portal).', why: 'A token is only for its intended recipient; signature alone does not prove that.', fail: 'Token for another client → rejected despite a valid signature.', scenarios: 'I6', evidence: 'Scenario Studio' },
  { name: 'Authorized party (azp)', what: 'For multi-audience tokens the authorized party must be this client; a present azp naming another client is rejected.', why: 'Stops a token authorized for a different party being reused here.', fail: 'azp mismatch → rejected (WRONG_AUDIENCE).', scenarios: '— (backend protocol tests)', evidence: 'Backend suite: test_azp_mismatch_rejected_for_multi_audience_token' },
  { name: 'Nonce', what: 'A random nonce is bound to the authorization request and must match the nonce claim in the ID token.', why: 'Stops replay of an ID token from another login attempt.', fail: 'Missing or wrong nonce → token rejected.', scenarios: 'I8', evidence: 'Scenario Studio' },
  { name: 'Expiry (exp)', what: 'exp is checked with a bounded 120s clock skew; expired tokens are rejected.', why: 'Stops stale credentials granting access.', fail: 'Expired token → rejected.', scenarios: 'I7', evidence: 'Scenario Studio' },
  { name: 'Issued-at (iat) & not-before (nbf)', what: 'iat is required and nbf is enforced (verify_nbf) within the same bounded skew.', why: 'Stops tokens used before they are valid or without a sane issuance time.', fail: 'Missing iat or a not-yet-valid token → rejected.', scenarios: '— (backend protocol tests)', evidence: 'Backend suite: validator unit tests' },
  { name: 'Subject (sub)', what: 'sub must be present; the validated subject is mapped to roles by trusted server-side policy, never from a browser claim.', why: 'Stops role spoofing via a forged or edited claim.', fail: 'Missing sub → rejected; spoofed officer role → denied (I13).', scenarios: 'I1, I13', evidence: 'Scenario Studio + Portal officer probe' },
  { name: 'Session policy', what: 'Sessions are opaque random IDs in HttpOnly cookies; rotation on login prevents fixation; logout revokes server-side; expiry is bounded.', why: 'Stops fixation, theft-by-cookie-reuse and stale sessions.', fail: 'Attacker-known session id is rotated away (I11); revoked session is denied (I12).', scenarios: 'I11, I12', evidence: 'Scenario Studio + Portal logout flow' },
  { name: 'CSRF (double-submit)', what: 'State-changing calls carry a double-submit token (cookie + x-csrf-token header) plus Origin/Referer checks; reset/logout rotate the token.', why: 'Stops cross-site requests from performing actions in the signed-in browser.', fail: 'Missing or mismatched token → 403 csrf_denied, nothing changes.', scenarios: 'I16', evidence: 'Scenario Studio + Portal logout-without-token test' },
  { name: 'Egress / SSRF guard', what: 'Issuer URLs must be in the allowlist and JWKS URLs must be loopback http(s), never metadata endpoints; backchannel calls ignore ambient proxy env vars.', why: 'Stops the backend being tricked into fetching attacker-controlled keys or cloud metadata.', fail: 'Off-allowlist issuer or JWKS URL → SSRF_BLOCKED.', scenarios: 'I18', evidence: 'Scenario Studio' },
]

export function ValidationRules() {
  return (
    <section aria-label="Validation Rules">
      <p className="eyebrow">Research · What the secure validator actually checks</p>
      <h1>Validation Rules</h1>
      <p className="page-sub">Each rule is enforced server-side and has a negative test that must reject the bad transaction <em>and</em> create no session. A rule that only logs a warning is not a rule. “Implemented” means the check exists in the secure validator; “tested” means a scenario or backend test exercises it — the two are listed separately so a gap is visible, not hidden.</p>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Validation rules table">
        <table>
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col">What is checked</th>
              <th scope="col">Why it matters</th>
              <th scope="col">Failure behaviour</th>
              <th scope="col">Negative scenario</th>
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {RULES.map((r) => (
              <tr key={r.name}>
                <td><strong>{r.name}</strong><br /><span className="badge badge-pass">IMPLEMENTED</span></td>
                <td>{r.what}</td>
                <td>{r.why}</td>
                <td>{r.fail}</td>
                <td>{r.scenarios}</td>
                <td className="small">{r.evidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>Not tested by a dedicated UI scenario</h2>
        <p>Two checks have no dedicated I-scenario in the Studio and are covered by the backend test suite instead: <strong>azp</strong> (multi-audience authorized party) and <strong>iat / nbf</strong> (issued-at / not-before). They are implemented in the secure validator and listed here with their backend test evidence — they are not claimed as “tested in the UI”.</p>
        <p className="small muted">Nothing in this lab is “tested” by assertion alone: run the scenario, watch the Atlas node stop at the exact rejection, and check the reason code.</p>
      </div>
    </section>
  )
}
