const TERMS = [
  { term: 'OAuth 2.0', def: 'A framework for delegated authorization: it lets an app act on your behalf with limited permission (a scope), without ever seeing your password. On its own, OAuth is not login — it does not say who you are.' },
  { term: 'OpenID Connect (OIDC)', def: 'An identity layer on top of OAuth 2.0. It adds an ID token — a signed statement from the identity provider saying who signed in, for which app, and when.' },
  { term: 'Authorization code + PKCE', def: 'The app redirects you to the identity provider; you sign in there; the provider returns a short-lived, single-use code to the app. PKCE adds a secret verifier (hashed into a challenge) so only the app that started the login can redeem the code. Think of it as a ticket plus a password only the buyer knows.', scenario: 'I3' },
  { term: 'State', def: 'A random value the app creates for one login attempt and checks when the provider replies. It ties the reply to the original request and stops an attacker starting a login in your browser.', scenario: 'I2' },
  { term: 'Nonce', def: 'A random value bound to one login attempt and carried inside the ID token. It stops an old ID token being replayed in a new login.', scenario: 'I8' },
  { term: 'Issuer (iss)', def: 'Who minted the token — the identity provider’s URL. The app only trusts its own allowlisted issuer.', scenario: 'I5' },
  { term: 'Audience (aud)', def: 'Who the token is for — the app’s client ID. A token minted for a different app must be rejected, even if its signature is valid.', scenario: 'I6' },
  { term: 'ID token vs access token', def: 'The ID token says who you are (for the app that requested login). The access token lets the app call an API on your behalf. Never use one as the other.' },
  { term: 'Redirect URI', def: 'The exact address the provider is allowed to send the code back to. It must match a registered value exactly — a look-alike address is not good enough.', scenario: 'I4' },
  { term: 'Authentication vs authorization', def: 'Authentication: proving who you are (signing in). Authorization: deciding what you may do (member vs officer). A signed-in student is authenticated but still not authorized for officer actions.', scenario: 'I13' },
]

export function Learning({ onOpenScenario }: { onOpenScenario?: (id: string) => void }) {
  return (
    <section aria-label="Learning Center">
      <p className="eyebrow">Evidence · Learn from what the lab actually measured</p>
      <h1>Learning Center</h1>
      <p className="page-sub">Plain-English explanations for a first-year cybersecurity student. Terms with a scenario link open that scenario so you can watch the check run; the remaining terms are concepts the checks rely on. See Validation Rules and Scenario Studio for the checks themselves.</p>
      <div className="grid">
        {TERMS.map((t) => (
          <article className="card" key={t.term}>
            <h2>{t.term}</h2>
            <p>{t.def}</p>
            {t.scenario && onOpenScenario && (
              <p><button type="button" className="btn btn-ghost" onClick={() => onOpenScenario(t.scenario!)}>See it in scenario {t.scenario}</button></p>
            )}
          </article>
        ))}
      </div>
      <div className="card">
        <h2>Try it yourself</h2>
        <p>1. Run I1 and watch the flow reach SESSION_CREATED. 2. Run I6 and find the step where the audience check rejects the token. 3. As student_01 in the Portal, try the officer resource and read the denial. Each step shows the exact reason code — that code is the lesson.</p>
        <p>
          {onOpenScenario && (<><button type="button" className="btn" onClick={() => onOpenScenario('I1')}>Open I1 — normal login</button>{' '}</>)}
          {onOpenScenario && (<><button type="button" className="btn btn-ghost" onClick={() => onOpenScenario('I6')}>Open I6 — wrong audience</button></>)}
        </p>
      </div>
      <div className="card">
        <h2>What this lab does not claim</h2>
        <p className="small muted">Finishing these scenarios does not certify you, this lab, or any real system as “secure”. It teaches you to read a rejection, find the exact check that fired, and prove a fix with a re-run — the working habits, not a credential.</p>
      </div>
    </section>
  )
}
