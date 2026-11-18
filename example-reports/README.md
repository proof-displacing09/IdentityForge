# Example Reports — IdentityForge

This folder holds the report schema template plus executed offline
reports from the release process.

- [`REPORT_TEMPLATE.json`](REPORT_TEMPLATE.json) — the report schema with
  every field marked `TEMPLATE`. It shows the shape of a run report
  (scenario id, mode, expected vs observed outcome, verifier decisions,
  transaction timeline, secure vs flawed results, resource-access
  outcome, reason code, elapsed time, evidence hash, status, limitations).
  No field in it is a measured result.
- [`executed-2026-11-09/verify-all.json`](executed-2026-11-09/verify-all.json)
  — executed I1–I18 offline runs from the v1 release (98-test backend).
- [`executed-2026-11-11/verify-all.json`](executed-2026-11-11/verify-all.json)
  — executed I1–I18 offline runs from the v2 release (130-test backend).
  These runs were executed with no evidence store, so each run reports
  `evidence_provenance: EPHEMERAL` and `evidence_saved: false` — the
  JSON file itself is the artifact; the runs were never persisted to
  the backend database. Their per-scenario session semantics match
  `docs/SCENARIO_METHOD.md` §9.

Real executed reports are added by the release process, one file per run,
named `<scenario_id>_<run_id>.json` (plus `.csv`/`.md` exports where
produced). Each executed report must:

- carry the correct `mode` label (`REAL KEYCLOAK`,
  `DETERMINISTIC OFFLINE FIXTURE`, or `PREVIOUS SAVED EVIDENCE`) and
  the correct `evidence_provenance` (`OFFLINE_FIXTURE`, `EPHEMERAL`,
  or `LIVE_KEYCLOAK`);
- contain no tokens, authorization codes, PKCE verifiers, session
  cookies, or passwords (search for `LabPass` — it must not appear);
- be listed in `docs/RELEASE_MANIFEST.md` with its run ID and date.

Never copy the template and present it as an executed result.
