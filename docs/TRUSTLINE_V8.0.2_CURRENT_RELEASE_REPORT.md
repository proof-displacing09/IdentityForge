# IdentityForge — Current-Release Report: Operation Trustline v8.0.2

**Release label:** v8.0.2 · **Target product version:** 1.8.2 · **Date:** 2026-11-13
**Status:** WS2 delivery (Fix B + Fix C). Parent Pass C re-verification and
packaging still to come — this report states what WS2 measured, and labels
everything it did not measure as NOT RUN.

> **Addendum (2026-11-13, Operation Trustline v8.0.3):** §10 below records
> the parent's Pass C outcome on the final v8.0.2 tree and final ZIP.
> Sections 1–9 are unchanged WS2 evidence from the v8.0.2 delivery;
> nothing in them was rewritten.

> **Read this first.** This report exists because the document the reviewer
> was given does not describe the archive it names. The external reviewer
> PDF names v8.0.1 but carries a historical v8 / product 1.8.0 cover and
> documents the old 352-file v8 ZIP with 482 backend tests, while the
> actual v8.0.1 archive is 364 files / 491 tests / version 1.8.1. This
> report is the correction for the *current* release, v8.0.2. It does not
> rewrite v8 history: every v8 figure in it is labelled historical v8,
> every v8.0.2 figure is labelled as measured on the v8.0.2 tree, and
> nothing in it is copied forward as a result it is not.
>
> **The ZIP hash is not in this document.** A SHA-256 is a property of
> the ZIP file itself, so it lives only in the delivery message, never
> inside the archive. Verify with `sha256sum <archive>` (Linux/macOS)
> or `Get-FileHash <archive> -Algorithm SHA256` (Windows PowerShell)
> against the delivery message before extracting.

## 1. What the reviewer was given vs what the archive actually is

| Claim | Source | Actual |
| ---- | ------ | ------ |
| v8 cover, product 1.8.0, 352 files, 482 backend tests | External reviewer PDF (names v8.0.1 on the cover page, documents v8) | That is the **v8** release (2026-11-13, product 1.8.0, 352 files, 482 backend tests). Correct as v8 history; wrong as a description of v8.0.1 or v8.0.2. |
| 364 files, 491 backend tests, version 1.8.1 | Delivered v8.0.1 archive (`IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.1_FINAL_20261113.zip`, SHA-256 `f130bced7…`) | Verified by the parent's Pass C on the actual ZIP bytes (three fresh extractions). |
| **520 backend tests (516 offline + 4 provider-dependent), 19 test-all gates, target version 1.8.2** | **This release, v8.0.2 (this report)** | Measured on the v8.0.2 tree by WS2 (see §3 and §8). The 51 WS3 depth tests are a separate count and are never added to the 520. |

There are **zero PDFs in the v8.0.1 archive** (`find . -name "*.pdf"` returns
nothing) and zero PDFs in the v8.0.2 tree before this report. Any PDF a
reviewer holds that is not this file is an external artifact, not a shipped
deliverable. This PDF was produced from the Markdown source shipped beside
it (`docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md`) — see §6 for the
tooling check and the regeneration command.

## 2. Which evidence is historical v8, and which belongs to v8.0.2

| Evidence | Belongs to | Status in v8.0.2 |
| ---- | ---- | ---- |
| Adversarial pentest: 16 findings (IF-V8-01–05, 40–45, 80–84), 11 fixed, 1 documented no-fix (IF-V8-04), 1 intended behaviour (IF-V8-82), 1 resolved concurrency artifact (IF-V8-45), 2 OPEN hardening (IF-V8-42, IF-V8-43). No CONFIRMED EXPLOITABLE finding. | **Historical v8** | Carried forward unchanged. The full record is `docs/FINAL_ADVERSARIAL_PENETRATION_TEST_REPORT.md` (§E/§M/§P) and `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md`. No pentest result was re-run or re-scored in v8.0.2. |
| Live gate `all` 101/101 + `reset` 69/69, full Playwright 72 passed + 1 skipped (validator PASS), axe 25/25 with 0 violations, Vitest 161/161, build byte-identical (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`) | **Historical v8.0.1 Pass C** | Carried forward as the last full-battery measurement. Not re-run by WS2 in v8.0.2; the parent's Pass C re-runs the battery on the final v8.0.2 tree. |
| Bounded IdP streaming (1 MiB+1 early stop, all four fetchers), 9 new streaming tests, 51 WS3 tests wired into CI, final-report §M/§L reconciliation | **v8.0.1** | Shipped in v8.0.1, unchanged in v8.0.2 except for the count arithmetic below. One disclosed precedence change carries over: declared Content-Length over 1 MiB + truncated body now raises `ValueError: size limit` instead of `RemoteProtocolError` (both are controlled `PROVIDER_ERROR` at the app layer; pinned by a test). |
| Offline pytest/CI fix (Fix B): `live_keycloak` marker, `-m "not live_keycloak"` offline selection, new `LIVE_PROVIDER_PYTEST` full-profile gate, `scripts/test-offline-provider-selection.sh` regression | **v8.0.2 (this release)** | Measured by WS2 — see §3. |
| IdP encoding work (Fix A) | **v8.0.2 (WS1)** | Observed by WS2 only: new file `backend/tests/adversarial/test_ws1_v802_idp_encoding.py` (29 collected tests). Full scope and evidence are in the WS1 handover, not this report. |
| This report + PDF (Fix C) | **v8.0.2 (this release)** | This document — see §6. |

## 3. Fix B — the offline pytest/CI defect, and its fix

### The defect (verified before the fix)

Four tests in `backend/tests/adversarial/test_ws1_v8_oidc.py` call
`GET /auth/login`, which fetches OIDC discovery from the live loopback
Keycloak (127.0.0.1:8080). With no provider running they fail with
503 `PROVIDER_UNAVAILABLE` — a missing-provider failure, not a product
failure. But every offline runner invoked unfiltered `python -m pytest -q`
while labelling the gate OFFLINE, so a correct tree failed its offline gates
whenever Keycloak was down:

- **Failing-first, the four tests:** with Keycloak up they pass (rc=0);
  with Keycloak stopped by exact PID they fail 4/4, each
  `assert 503 == 302` with
  `{"detail":"provider_unavailable","reason":"PROVIDER_UNAVAILABLE"}` (rc=1).
- **Failing-first, verify-release:** fresh extraction of the delivered
  v8.0.1 ZIP (364 entries, testzip clean), dependencies on PATH, Keycloak
  absent: `verify-release.sh` reads **22 PASS / 1 FAIL / 5 NOT RUN, rc=1**,
  sole FAIL `BACKEND_PYTEST`.

### The fix

- The four tests carry `@pytest.mark.live_keycloak`
  (`test_callback_replay_and_cross_browser_and_errors`,
  `test_callback_replay_after_consume`, `test_login_start_rate_limit`,
  `test_login_start_sets_browser_cookie_and_s256`). The marker is registered
  in `backend/pytest.ini` (the effective pytest config). Markers only — no
  test logic, assertion, fixture, or production code changed; no test was
  removed, skipped silently, weakened, or stubbed away.
- One named offline selection, `-m "not live_keycloak"`, in all three
  offline runners: the default CI backend lane (`.github/workflows/ci.yml`),
  `scripts/test-all.sh` `OFFLINE_UNIT`, and `scripts/verify-release.sh`
  `BACKEND_PYTEST`.
- The marked tests run only in the full profile: new `test-all.sh --full`
  gate `LIVE_PROVIDER_PYTEST` (`-m live_keycloak`, against the cold-started
  disposable Keycloak, only when the cold-start boot succeeded; otherwise
  NOT RUN honestly). In CI they run in the `keycloak-e2e` lane, which runs
  `test-all.sh --full --strict`. Gate count 18 → **19** (12 offline + 7 full).
- New regression `scripts/test-offline-provider-selection.sh` (wired into
  the CI scripts lane, offline mode), proving (a) the offline selection
  passes with no provider and the deselected set is exactly the four tests,
  and (b) the live lane wiring still runs all four (statically in every
  mode; `--live` runs them against a real provider and requires 4 passed).
  No count is hardcoded in the suite — it counts the split dynamically.

### Measured results (WS2, v8.0.2 tree)

| Check | Result |
| ---- | ------ |
| Backend suite | **520 collected = 516 offline + 4 `live_keycloak`** (the four IDs are exactly the expected four; the 51 WS3 tests are separate and never added). Baseline v8.0.1 was 491; WS1's Fix A adds 29. |
| Offline/provider regression | **11/11 PASS offline mode** (no provider on 8080; offline selection passes, 516 tests, rc=0) and **11/11 PASS live mode** (live Keycloak discovery 200, canonical issuer; live selection passes, 4 tests, rc=0). |
| `test-all.sh --offline` (final tree) | **rc=0 — 11 PASS / 0 FAIL / 8 NOT RUN across the 19 gates.** NOT RUN: full `npm audit` (registry 403) + the 7 full-profile gates. |
| `verify-release.sh` (final tree, Keycloak absent) | **23 PASS / 0 FAIL / 5 NOT RUN, rc=0.** `BACKEND_PYTEST`, `DOCS_CONTRACT`, `DOCS_CONTRACT_PATHS` all PASS. The 5 NOT RUN are the bare-extraction deps/Docker checks. |
| Docs-contract / docs-contract paths | **PASS, 0 violations** (34 FailureReason values, 59 report-model fields, 123 source files, 70 files scanned) / **48/48**. |
| CI YAML | Syntax valid (4 jobs: backend, frontend, scripts, keycloak-e2e). **GitHub Actions execution NOT RUN** — no CI run has occurred; a YAML-valid workflow is not an executed one. |

## 4. Fix A (WS1) — what WS2 observed

WS1's Fix A (IdP encoding) lands in the same tree: new test file
`backend/tests/adversarial/test_ws1_v802_idp_encoding.py` (29 collected
tests) and changes to `backend/src/identityforge/protocol/jwks.py` and
`backend/tests/fake_http.py`, which WS1 owns and WS2 did not touch. The
backend suite grows 491 → 520 on that account. WS2 verified the arithmetic
(516 + 4 = 520; the four `live_keycloak` IDs unchanged) but did not audit
Fix A's substance — its scope and evidence are in the WS1 handover, and
the parent's Pass C re-runs the full battery on the merged tree.

## 5. Version honesty — what 1.8.2 means in this report

The target product version for the packaged v8.0.2 archive is **1.8.2**.
The in-tree code still reports **1.8.1** at the time WS2's work lands
(`backend/src/identityforge/__init__.py`, `backend/pyproject.toml`,
`frontend/package.json` + `package-lock.json`, and the running backend's
`/api/v1/health`, which WS2 observed reporting 1.8.1). The 1.8.2 contract
bump — code sources, `scripts/check-version-contract.py` (which still reads
the Trustline v8.0.1 manifest section and expects 1.8.1 by default),
`scripts/test-version-contract.sh` fixtures, and the test-only version
assertions — is applied by the coordinator at packaging, following the
v8.0.1 precedent. Until that bump lands, `VERSION_CONTRACT` in this tree
verifies 1.8.1, and every "1.8.2" in this report and in the manifest's
v8.0.2 section is the **target** version for the packaged archive, not a
claim about the current in-tree code. After packaging, verify it the same
way v8.0.1 was verified: `GET /api/v1/health` must report 1.8.2, and
`python3 scripts/check-version-contract.py` must pass at 1.8.2.

## 6. How this PDF was made (Fix C tooling check)

The directive was: a PDF if real tooling is available and verifiable;
otherwise a clearly labelled Markdown addendum, with the reason stated
plainly and never faked. Real tooling **is** available:

| Tool | Result in this sandbox |
| ---- | ------ |
| reportlab / weasyprint / pandoc / wkhtmltopdf / LaTeX | **Not installed** (no such modules/binaries). |
| LibreOffice 24.2 (`soffice --headless --convert-to pdf`) | **Available and verified.** A probe HTML converted to a real PDF (Producer LibreOffice 24.2), text-extractable with `pdftotext`, Unicode intact. |
| markdown-it-py 4.3.0 (in the v7.3.1 venv) | **Available.** Markdown → HTML conversion for this report. |

Pipeline (reproducible from the shipped tree — the build script is
`scripts/build-current-release-report.py`):

```bash
~/workspace/identityforge-v7.3.1/.venv/bin/python scripts/build-current-release-report.py
pdfinfo docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.pdf
pdftotext docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.pdf - | head
```

The script converts the Markdown with markdown-it-py, wraps it in print
CSS, and calls `soffice --headless --convert-to pdf` (the HTML intermediate
goes to a temp dir, never into the tree). The shipped PDF was produced
exactly this way and verified: 10 pages, A4, Producer LibreOffice 24.2,
text-extractable (`pdftotext` finds the §1 table, the §3 results, and the
§8 commands). Check the byte size and hash of the file you hold against
the delivery message, not against a number printed in the document —
both are properties of the generated file.

## 7. Residual risks and open items

- **IF-V8-42 (Dockerfiles run as root) and IF-V8-43 (CI SHA pins) stay
  OPEN.** Neither is claimed fixed. Each carries a reviewer checklist in
  `docs/PENTEST_FINDINGS_AND_REMEDIATIONS.md` stating exactly what must be
  observed before closing (Docker boot + volume-permission regression checks
  against the final image for 42; upstream SHA verification + an observed CI
  run for 43). No Docker/CI pass is claimed in this release.
- **`test-all.ps1` follow-up is OPEN.** `test-all.ps1` still defines 18
  gates (vs 19 for `test-all.sh`) and its `OFFLINE_UNIT` still runs
  unfiltered `pytest -q` inside the backend-test container, which has no
  IdP — the same defect class Fix B repaired on the sh/CI/verify-release
  path. The ps1 `-Full` live run of the four tests additionally needs a
  container with provider access (the backend-test container has no
  Keycloak route; the `live-gate` container pattern with the host map is
  the existing precedent). On Windows, treat a ps1 `OFFLINE_UNIT` failure
  naming the four `live_keycloak` tests as the known missing-provider shape,
  not a product failure, until that follow-up lands. `docs/WINDOWS_SETUP.md`
  records this divergence.
- **Reviewer gates NOT RUN:** Docker Compose boot, Windows PowerShell 5.1
  execution, the in-image Keycloak healthcheck, and the full `npm audit`
  were NOT RUN in the build sandbox (no Docker binary/socket; 5.1 is
  Windows-only; `npm audit` registry 403). The GHSA direct-only check is
  not a substitute for the full audit.
- **Source-level mutation testing NOT RUN by design** (standing instruction);
  sensitivity is proven through throwaway fixture-level fault injection.
- **No second pentest was performed in v8.0.2.** Fix B and Fix C are
  targeted repairs and reporting; the adversarial findings above are
  historical v8, not re-tested here.

## 8. How to verify this release (reviewer commands)

```bash
# 1. Hash first, before extracting (hash from the delivery message only):
sha256sum IdentityForge_OAuth_OIDC_Complete_Source_TRUSTLINE_V8.0.2_FINAL_20261113.zip
# 2. Extract with Info-ZIP unzip (preserves the .sh exec bit), then:
bash scripts/verify-release.sh            # expect 23/0/5 with deps installed; BACKEND_PYTEST must PASS
./scripts/test-all.sh --offline           # expect rc=0; 11 PASS / 0 FAIL / 8 NOT RUN across 19 gates
# 3. Test counts (backend/, venv python with PYTHONPATH=src):
python -m pytest --collect-only -q -m "not live_keycloak"   # 516 collected
python -m pytest --collect-only -q -m live_keycloak         # 4 collected, exactly the four tests in §3
# 4. Full profile (needs Docker Desktop; boots a disposable stack):
./scripts/test-all.sh --full --strict     # LIVE_PROVIDER_PYTEST must PASS against the disposable Keycloak
# 5. Version (after the packaging bump, §5):
curl -s http://127.0.0.1:8000/api/v1/health   # "version" must read 1.8.2
python3 scripts/check-version-contract.py     # must pass at 1.8.2
```

## 9. Evidence index (WS2, v8.0.2)

All files live in `~/workspace/ws2-v802-evidence/` (outside the archive;
raw logs are never shipped inside the ZIP):

| File | What it proves |
| ---- | ---- |
| `four-tests-live-pass.txt` | Four tests pass with Keycloak up (rc=0). |
| `four-tests-no-keycloak-fail.txt` | Four tests fail with Keycloak absent, each 503 `PROVIDER_UNAVAILABLE` (rc=1). |
| `verify-release-fresh-nokeycloak.txt` | v8.0.1 fresh extraction, no Keycloak: 22/1/5, sole FAIL `BACKEND_PYTEST`. |
| `verify-release-fixed-nokeycloak.txt` | Fixed tree, pre-docs: 22/1/5, `BACKEND_PYTEST` PASS, sole FAIL `DOCS_CONTRACT` (check-7 intermediate state). |
| `verify-release-final2.txt` | Final tree, no Keycloak: **23/0/5, rc=0**. |
| `regression-offline.txt` / `regression-live.txt` | `test-offline-provider-selection.sh` 11/11 PASS in both modes. |
| `regression-offline-final.txt` / `four-tests-live-final.txt` | Final re-runs on the finished tree: offline regression 11/11 PASS; the four `live_keycloak` tests pass against the restarted live Keycloak (rc=0). |
| `docs-contract-final.txt` / `docs-contract-final2.txt` | Docs-contract PASS (0 violations), before and after the report/log edits. |
| `keycloak-v802-restart3.log`, `counts-after-live-ws2.json` | Final live-stack restart (discovery 200, issuer exact) and the post-run dev-counts snapshot. The dev backend's counts moved from all-zero (pre-live snapshot) to 36 runs / 18 live logins / 62 events because `test-all.sh --offline`'s `OFFLINE_SCENARIOS` gate writes scenario runs to the working copy's dev DB (`backend/data/identityforge.db`). No reset was performed against the dev backend (resets run only against disposable marker backends on temp DBs); the DB is excluded from the packaged archive (`*.db`), so nothing ships with these counts. |
| `docs-contract-final.txt` / `docs-contract-paths-final.txt` | Docs-contract PASS (0 violations) / paths 48/48. |
| `test-all-offline-final2.txt` (and `test-all-offline-final.txt`) | `test-all.sh --offline` 11/0/8 (clean run); first run 10/0/9 with the PATH/PyYAML artifact, explained in the log section. |
| `diff-vs-v801.txt` | File-level diff of the v8.0.2 tree against the delivered v8.0.1 ZIP. |
| `keycloak-v802*.log`, `backend-v802.log`, `counts-before-live-ws2.json` | Live-stack restarts, health, and the pre-live dev-counts snapshot (all zero). |

## 10. Addendum — parent Pass C outcome on the final v8.0.2 tree (2026-11-13, recorded in v8.0.3)

This section was appended in Operation Trustline v8.0.3. Sections 1–9
above are unchanged WS2 evidence from the v8.0.2 delivery; nothing in
them was rewritten. What follows is the parent's own Pass C measurement
on the final v8.0.2 tree and the final v8.0.2 ZIP — the verification
that was still to come when §§1–9 were written.

| Check | Result (parent's Pass C, final v8.0.2 tree) |
| ---- | ------ |
| Backend pytest (full) | **520 passed, rc=0.** |
| pytest offline selection, Keycloak ABSENT | **516 passed, 4 deselected, rc=0** (`-m "not live_keycloak"`). |
| pytest live selection, Keycloak PRESENT | **4 passed, 516 deselected, rc=0** (`-m live_keycloak`). |
| WS3 depth tests (separate count) | **51 passed, rc=0.** |
| CLI verify-all | **18/18 PASS.** |
| ruff check / format | **clean, 68 files.** |
| typecheck | **PASS (rc=0).** |
| Vitest | **161/161.** |
| frontend build | **byte-identical to v8** (`index-X2bsjLBG.js`, SHA-256 `a77dd7d5…`). |
| version-contract / docs-contract | **PASS 1.8.2 / PASS, 0 violations.** |
| docs-contract paths | **48/48.** |
| dependency gates | **55/0.** |
| `test-all.sh --offline` | **rc=0, 11 PASS / 0 FAIL / 8 NOT RUN across the 19 gates** (NOT RUN: full `npm audit` registry 403 + 7 full-profile gates incl. LIVE_PROVIDER_PYTEST). |
| healthcheck regressions | **34/0/0.** |
| PowerShell matrix (pwsh 7.4.6 on Linux) | **26/0/0.** |
| live gate `all` | **101/101, rc=0** (real Keycloak). |
| live gate `reset` | **69/69, rc=0** (disposable marker backend `6bbca7ad-…`; dev counters byte-identical on restore). |
| guard negatives | **no-flag rc=2 / wrong-id rc=1 / malformed rc=2** (dev counts untouched). |
| full Playwright | **72 passed + 1 skipped, rc=0**; validator **PASS**. |
| axe (a11y, zero-tolerance) | **25/25, 0 violations.** |
| CI YAML | **valid, 4 jobs** (backend, frontend, scripts, keycloak-e2e). **GitHub Actions execution NOT RUN.** |

Final v8.0.2 ZIP (delivered 2026-11-13): **369 files, 42,195,522 bytes,
SHA-256 `af951f830d3436635d4b1de1ade5728849952d64c2a36f5eb6a70dcd535247cb`**.
(The v8.0.2 archive is already delivered, so its hash is a historical
fact; the v8.0.3 archive's own hash is, as §1 states, only in the
delivery message, never inside the archive.) `verify-release.sh` read
**23 PASS / 0 FAIL / 5 NOT RUN, rc=0 in all three fresh extractions**
of the actual final ZIP bytes (plain, path with spaces, path under an
ancestor literally named `data/`), and re-verified 23/0/5 ×3 after
re-packaging. Plain-extraction deep check: pytest 520, CLI 18/18,
docs-paths 48/48, dep-gates 55/0, regressions 32/0/2, `npm ci` +
Vitest 161/161 + build byte-identical.

Double-run incident (not a ZIP defect): the first verification pass ran
verify-release twice in the same extraction directories and the second
run read 22/1/5 with FORBIDDEN_FILES FAIL on
`backend/data/identityforge.db` — a database the first run's own
BACKEND_PYTEST had created in that extraction (the ZIP namelist holds
no DB; a fresh extraction has no `backend/data/` at all). Re-extracted
fresh and ran once per directory: 23/0/5 rc=0 in all three. In v8.0.3,
`verify-release.sh` BACKEND_PYTEST isolates that side effect to a
disposable temp directory, so a second run in the same extraction no
longer false-fails (see `docs/VERIFICATION_LOG.md`, Operation
Trustline v8.0.3 section); a fresh extraction per run is still the
recommended audit shape.

Open follow-up from §7, now closed in v8.0.3: the `test-all.ps1`
follow-up (18 gates, unfiltered OFFLINE_UNIT) is fixed by WS1 in this
round — `test-all.ps1` now defines the same 19 gates as `test-all.sh`,
its OFFLINE_UNIT runs `-m "not live_keycloak"`, and the full profile
adds LIVE_PROVIDER_PYTEST. Windows PowerShell 5.1 execution of the
fixed runner remains NOT RUN (5.1 is Windows-only) — the reviewer
gate. IF-V8-42/43 stay OPEN.

*End of addendum — Operation Trustline v8.0.3, WS2, 2026-11-13.*

*End of report — Operation Trustline v8.0.2, WS2 (Fix B + Fix C), 2026-11-13.*
