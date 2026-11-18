# GitHub Action SHA Pins (IF-V8-43)

Every external GitHub Action used by `.github/workflows/ci.yml` is pinned
to a **full 40-character commit SHA** with a human-readable `# vX.Y.Z`
comment naming the exact release tag the SHA was resolved from. A major
tag (`@v4`) or a semver tag (`@v4.4.0`) is mutable upstream: whoever
controls the tag can move it. A SHA cannot be moved. If a pinned SHA
ever needs to change, resolve the new release the same way (below) and
update this doc, the checker (`scripts/test-action-pins.sh`, which holds
the same mapping as its source of truth and fails CI if this doc drifts
from it), and every `uses:` line for that action.

## The pins

| Action | Release tag | Full commit SHA | `uses:` line |
| ------ | ----------- | --------------- | ------------ |
| `actions/checkout` | v4.4.0 | `11d5960a326750d5838078e36cf38b85af677262` | `actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4.4.0` |
| `actions/setup-python` | v5.6.0 | `a26af69be951a213d495a4c3e4e4022e16d87065` | `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0` |
| `actions/setup-node` | v4.4.0 | `49933ea5288caeca8642d1e84afbd3f7d6820020` | `actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020  # v4.4.0` |
| `actions/upload-artifact` | v4.6.2 | `ea165f8d65b6e75b540449e92b4886f43607fa02` | `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02  # v4.6.2` |

Where each action is used (11 `uses:` lines, all pinned, one identical
SHA per action):

- `actions/checkout` — backend, frontend, scripts, keycloak-e2e lanes
  (ci.yml lines 76, 132, 193, 420).
- `actions/setup-python` — backend, scripts, keycloak-e2e lanes
  (lines 78, 195, 422).
- `actions/setup-node` — frontend, scripts, keycloak-e2e lanes
  (lines 134, 206, 426).
- `actions/upload-artifact` — keycloak-e2e lane only (line 447).

No other workflow file exists under `.github/workflows/` (only
`ci.yml`), and no reusable workflow, nested action, or `docker://`
reference is used. No `uses:` line anywhere in the repo still uses a
mutable `@vN` / `@vN.N.N` reference.

## How each SHA was verified (2026-11-14, upstream, no third-party list)

For each action, the intended release is the **latest patch release
within the same major line already in use** — no major-version jump
(checkout stays on v4, setup-python on v5, setup-node on v4,
upload-artifact on v4). Each SHA was resolved directly from the
official upstream repository `github.com/actions/<action>` through
**three independent GitHub API surfaces that all agree**, plus the
release record:

1. `GET /repos/actions/<repo>/tags?per_page=100` — the tag list;
   the entry for the release tag names the commit SHA.
2. `GET /repos/actions/<repo>/git/ref/tags/<tag>` — the ref itself.
   For all four actions the ref type is `commit`, i.e. these are
   **lightweight tags: the tag object IS the commit**, so there is no
   separate annotated-tag object to dereference. (Had any tag been
   annotated, the proof chain would have been tag ref -> tag object
   -> `object.sha` commit; the checker evidence log records the type
   observed so a future re-verification can tell which case applied.)
3. `GET /repos/actions/<repo>/commits/<sha>` — the commit exists
   upstream, with its date and message.
4. `GET /repos/actions/<repo>/releases/tags/<tag>` — a published,
   non-draft, non-prerelease release with that tag name.

Per-action evidence (all fetched 2026-11-14; raw responses saved in
the WS2 evidence bundle, `~/workspace/ws2-v805-evidence/`):

| Action | Tag | SHA | Ref type | Commit date / message (first line) | Release published |
| ------ | --- | --- | -------- | ---------------------------------- | ----------------- |
| `actions/checkout` | v4.4.0 | `11d5960a326750d5838078e36cf38b85af677262` | `commit` (lightweight) | 2026-07-16 — `backport fixes to releases-v4 (#2524)` | 2026-07-20 |
| `actions/setup-python` | v5.6.0 | `a26af69be951a213d495a4c3e4e4022e16d87065` | `commit` (lightweight) | 2025-04-24 — `Bump ts-jest from 29.1.2 to 29.3.2 (#1081)` | 2025-04-24 |
| `actions/setup-node` | v4.4.0 | `49933ea5288caeca8642d1e84afbd3f7d6820020` | `commit` (lightweight) | 2025-04-02 — `Bump @action/cache from 4.0.2 to 4.0.3 (#1262)` | 2025-04-14 |
| `actions/upload-artifact` | v4.6.2 | `ea165f8d65b6e75b540449e92b4886f43607fa02` | `commit` (lightweight) | 2025-03-19 — `Merge pull request #685 from salmanmkc/salmanmkc/3-new-upload-artifacts-release` | 2025-03-19 |

Cross-checks:

- The checkout SHA additionally matches an independent
  `git ls-remote https://github.com/actions/checkout.git refs/tags/v4`
  probe run by the coordinator in the same round, which returned
  `11d5960a326750d5838078e36cf38b85af677262` — the major tag `v4`
  currently points at the v4.4.0 commit, as expected.
- The tags-list major-tag entries agree too: `v4` -> the checkout
  v4.4.0 SHA, `v5` -> the setup-python v5.6.0 SHA, `v4` -> the
  setup-node v4.4.0 SHA, `v4` -> the upload-artifact v4.6.2 SHA.
  (Major tags are recorded here as evidence only; CI pins the SHAs.)
- `git ls-remote` over the git protocol was **not** usable as the
  primary method in this sandbox: it timed out at 240 s twice
  (2026-11-14) while the HTTPS API answered each call in under a
  second. The API is an official upstream surface, so this is not a
  weaker proof — it is the same repository, read three ways.

## Checker

`scripts/test-action-pins.sh` (offline, no Docker, no network) runs in
the CI scripts lane and fails the lane on:

- any `uses:` line not pinned to a full 40-hex SHA;
- a SHA that differs from this doc's mapping for that action;
- a missing `# vX.Y.Z` comment, or one naming a different tag;
- any external action not in the mapping (fail-closed on new actions);
- this doc drifting from the checker's mapping.

Its built-in negative control builds a fixture workflow with six
defects (major tag, semver tag, truncated 39-hex SHA, correct SHA with
no comment, correct SHA with the wrong comment, unmapped action) and
requires all six to be rejected. Local proof: run
`bash scripts/test-action-pins.sh` — it prints the per-line verdicts
and a `PASS`/`FAIL` tally.

## Status

**SHA PIN VERIFIED, HOSTED CI PENDING.** Every SHA above is
upstream-verified by the method in this doc. GitHub-hosted Actions
execution of the pinned workflow is NOT RUN in this sandbox (no
GitHub repository access from here, and the workflow was never pushed
by this work — see "Reviewer steps" below). A YAML-valid workflow is
not an executed one.

## Reviewer steps (owner runs these; do not push from the sandbox)

1. Create a test branch from the delivered tree and push it to the
   repository, e.g.:
   `git checkout -b trustline-v805-action-pins && git push -u origin trustline-v805-action-pins`
   (or open a pull request from that branch to `main` — either
   triggers the default push/PR run of the backend, frontend, and
   scripts lanes).
2. In the repository's **Actions** tab, open the run for that branch
   and confirm all three default jobs are green: **backend**,
   **frontend**, **scripts** (the scripts lane now has 26 steps; the
   new step is `Action SHA pins (IF-V8-43, v8.0.5)`).
3. Record the run URL and run ID, and confirm the run used the pinned
   SHAs: open a job's setup logs (e.g. the `Set up job` / action
   download lines) and check the resolved action versions name the
   SHAs in the table above.
4. Optionally trigger the manual lane: **Actions > CI >
   Run workflow** on the same branch (`workflow_dispatch`), confirm
   the **keycloak-e2e** job runs `test-all.sh --full --strict` and
   record its result separately — a green default run is never
   live-Keycloak proof.
5. Copy the run URL, run ID, per-job status, and the SHA confirmation
   into `docs/VERIFICATION_LOG.md` (and the IF-V8-43 closing entry in
   `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`). Only then does
   IF-V8-43 move from `SHA PIN VERIFIED, HOSTED CI PENDING` to
   `FIXED, verified post-fix`.
