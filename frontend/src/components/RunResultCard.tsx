import type { RunResult } from '../types'
import { ModeBadge, ModelBadge, ProvenanceBadge, StatusBadge } from './Badge'

function yesNo(v: boolean | undefined): string {
  return v === true ? 'Yes' : v === false ? 'No' : 'Unknown'
}

/** One run, honestly rendered (P0-06): the decision badges, the ACTUAL
 *  session state transitions the run observed, the flawed model's
 *  status, and the evidence provenance. An unsaved/ephemeral run never
 *  displays "saved". */
export function RunResultCard({ run }: { run: RunResult }) {
  return (
    <article className="card" aria-label={`Result for ${run.scenario_id}`}>
      <h3>{run.scenario_id} — {run.title}</h3>
      <p><StatusBadge status={run.status} /> <ModeBadge mode={run.mode} /> <ProvenanceBadge provenance={run.evidence_provenance} /> <ModelBadge status={run.flawed_model_status} /></p>
      <dl className="kv">
        <dt>Expected</dt><dd>{run.expected_outcome}</dd>
        <dt>Secure variant</dt><dd>{run.observed_secure}</dd>
        <dt>Flawed fixture</dt><dd>{run.observed_flawed}</dd>
        <dt>Validation reason</dt><dd><span className="code">{run.validation_reason}</span></dd>
        <dt>Resource access</dt><dd>{run.resource_access_outcome}</dd>
        <dt>Elapsed</dt><dd>{run.elapsed_ms} ms · {run.timestamp}</dd>
        <dt>Run ID</dt><dd><span className="code">{run.run_id}</span></dd>
        <dt>Evidence</dt>
        <dd>
          {run.evidence_saved === true
            ? 'Saved by the backend'
            : run.evidence_saved === false
              ? `NOT SAVED${run.evidence_error ? ` — ${run.evidence_error}` : ''}`
              : 'Unknown (run predates evidence reporting)'}
        </dd>
      </dl>
      <h4>Session &amp; model state — what actually happened</h4>
      <dl className="kv">
        <dt>Secure session created</dt><dd className="session-state">{yesNo(run.secure_session_created)}</dd>
        <dt>Flawed session created</dt>
        <dd className="session-state">
          {run.flawed_model_status === 'NOT_MODELED' ? 'Not modeled for this scenario' : yesNo(run.flawed_session_created)}
        </dd>
        <dt>Session preexisted</dt><dd className="session-state">{yesNo(run.session_preexisted)}</dd>
        <dt>Session revoked</dt><dd className="session-state">{yesNo(run.session_revoked)}</dd>
        <dt>Guard omitted (flawed)</dt>
        <dd>{run.flawed_guard_omitted ? <span className="code">{run.flawed_guard_omitted}</span> : '—'}</dd>
        <dt>Flawed observed result</dt><dd>{run.flawed_observed_result || '—'}</dd>
        <dt>Protected resource disclosed</dt>
        <dd>
          {run.protected_resource_disclosed === true
            ? <span className="badge badge-fail">YES — disclosed to an actor who must not have it</span>
            : run.protected_resource_disclosed === false
              ? 'No'
              : 'Unknown'}
        </dd>
      </dl>
      {run.timeline?.length > 0 && (
        <>
          <h4>Timeline</h4>
          <ol className="timeline">
            {run.timeline.map((s, i) => (
              <li key={i} className={/reject|fail|denied/i.test(s.outcome) ? 'rejected' : ''}>
                <span className="step">{s.step}</span> — {s.outcome}
                {s.reason ? <span className="muted"> ({s.reason})</span> : null}
              </li>
            ))}
          </ol>
        </>
      )}
    </article>
  )
}
