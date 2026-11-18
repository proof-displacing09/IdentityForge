#!/usr/bin/env python3
"""Validate a Playwright JSON report as E2E evidence (IF-V4-10, v5).

The runners used to treat a successful Playwright exit code as PASS
without parsing what actually executed — a whole-suite skip (lab
down, provider down) looked identical to a full pass. This validator
parses the JSON report (see frontend/playwright.config.ts, which
emits test-results/playwright-report.json) and fails closed unless
the report proves real execution against the just-booted project:

e2e profile (portal + edge + a11y, the `npm run test:e2e` run):
  * the report parses and carries the expected target project
    (config.metadata.target == --target) and base URL;
  * the report is fresh (file mtime >= --since-epoch when given —
    the runner deletes any pre-existing report before the run and
    passes the run-start epoch);
  * minimum executed counts per spec file (floors, not exact counts,
    so a future added test does not break the gate);
  * the four named real-login/discovery tests PASSED:
    - Keycloak discovery issuer is the pinned canonical issuer
    - student_01: member 200, officer 403
    - logout revokes the session; stale cookie is denied (401)
    - officer_01: member 200 and officer 200
  * zero failed / timed-out / flaky specs;
  * the ONLY permitted skip is the one documented honest skip:
    'user cancels at the Keycloak login page' (the Keycloak login
    page offers no cancel control in this realm — see
    frontend/e2e/edge.spec.ts). Any other skip fails the gate.

screenshots profile (the `npm run test:screenshots` run, which
overwrites the same report file — so the runners validate the E2E
report BEFORE starting the screenshots run):
  * same target/freshness checks;
  * every spec passed, zero skipped/failed/timed-out;
  * at least one 'screenshots @ <viewport>' and one
    'settings + reset modal @ <viewport>' spec passed.

Exit codes: 0 = PASS (evidence proves execution), 1 = FAIL.
Usage:
  python3 scripts/validate-playwright-report.py --report <json>
      --target <project> [--profile e2e|screenshots]
      [--since-epoch <unix-seconds>] [--base-url <url>]
"""

import argparse
import json
import os
import sys

# The one documented honest skip (see frontend/e2e/edge.spec.ts).
ALLOWED_SKIP_TITLE = "user cancels at the Keycloak login page"
ALLOWED_SKIP_REASON = "no cancel control"

# Exact titles of the named real-login/discovery tests that must PASS.
REQUIRED_PASSED_E2E = [
    "Keycloak discovery issuer is the pinned canonical issuer",
    "student_01: member 200, officer 403",
    "logout revokes the session; stale cookie is denied (401)",
    "officer_01: member 200 and officer 200",
]

# Floors (not exact counts): a future added test must not break the gate.
MIN_TOTAL_E2E = 40
MIN_PASSED_PER_FILE_E2E = {
    "portal.spec.ts": 8,
    "edge.spec.ts": 8,
    "a11y.spec.ts": 24,
}
MIN_TOTAL_SCREENSHOTS = 20

EXPECTED_BASE_URL = "http://127.0.0.1:5173"


def walk_specs(suites, out):
    """Flatten the nested Playwright suites into (file, title, status, timed_out)."""
    for suite in suites or []:
        for spec in suite.get("specs", []):
            title = spec.get("title", "")
            tests = spec.get("tests", [])
            # A spec normally has one test entry; take the worst status.
            status = "skipped"
            timed_out = False
            for t in tests:
                st = t.get("status", "")
                for r in t.get("results", []):
                    if r.get("status") == "timedOut":
                        timed_out = True
                if st == "unexpected":
                    status = "unexpected"
                elif st == "flaky" and status != "unexpected":
                    status = "flaky"
                elif st == "expected" and status not in ("unexpected", "flaky"):
                    status = "expected"
                elif st == "skipped" and status not in ("unexpected", "flaky", "expected"):
                    status = "skipped"
            out.append({
                "file": suite.get("file", ""),
                "title": title,
                "status": status,
                "timed_out": timed_out,
            })
        walk_specs(suite.get("suites", []), out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate a Playwright JSON report (IF-V4-10).")
    ap.add_argument("--report", required=True, help="path to playwright-report.json")
    ap.add_argument("--target", required=True, help="expected config.metadata.target (disposable project)")
    ap.add_argument("--profile", choices=["e2e", "screenshots"], default="e2e")
    ap.add_argument("--since-epoch", type=float, default=0,
                    help="report file mtime must be >= this unix epoch (0 = skip freshness check)")
    ap.add_argument("--base-url", default=EXPECTED_BASE_URL,
                    help="expected config.metadata.baseURL (default %(default)s)")
    args = ap.parse_args(argv)

    failures = []
    notes = []

    if not os.path.isfile(args.report):
        print(f"PLAYWRIGHT_VALIDATOR: FAIL report missing: {args.report} (no Playwright JSON evidence — the E2E run produced no report)")
        return 1
    if args.since_epoch > 0:
        mtime = os.path.getmtime(args.report)
        if mtime < args.since_epoch:
            print(f"PLAYWRIGHT_VALIDATOR: FAIL report is stale: {args.report} mtime {mtime:.0f} < run start {args.since_epoch:.0f} — a pre-existing report, not this run's evidence")
            return 1
    try:
        with open(args.report, encoding="utf-8") as fh:
            report = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"PLAYWRIGHT_VALIDATOR: FAIL report is not valid JSON: {args.report}: {exc}")
        return 1
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        print(f"PLAYWRIGHT_VALIDATOR: FAIL report has no 'suites' list — not a Playwright JSON report: {args.report}")
        return 1

    metadata = report.get("config", {}).get("metadata", {}) or {}
    got_target = metadata.get("target")
    if got_target != args.target:
        failures.append(
            f"target mismatch: report metadata.target is {got_target!r}, expected {args.target!r} "
            f"(the run pointed at a different project / stale stack, not the just-booted disposable project)")
    got_base = metadata.get("baseURL")
    if got_base != args.base_url:
        failures.append(f"baseURL mismatch: report metadata.baseURL is {got_base!r}, expected {args.base_url!r}")

    specs = []
    walk_specs(report["suites"], specs)
    total = len(specs)
    passed = sum(1 for s in specs if s["status"] == "expected")
    failed = [s for s in specs if s["status"] == "unexpected"]
    flaky = [s for s in specs if s["status"] == "flaky"]
    skipped = [s for s in specs if s["status"] == "skipped"]
    timed_out = [s for s in specs if s["timed_out"]]
    by_file_passed = {}
    for s in specs:
        if s["status"] == "expected":
            by_file_passed[s["file"]] = by_file_passed.get(s["file"], 0) + 1

    summary = (f"total={total} passed={passed} failed={len(failed)} "
               f"skipped={len(skipped)} timedOut={len(timed_out)} flaky={len(flaky)}")

    if args.profile == "e2e":
        if total < MIN_TOTAL_E2E:
            failures.append(f"too few specs executed: total {total} < floor {MIN_TOTAL_E2E} "
                            f"(a whole-suite skip or a truncated run must not pass)")
        for fname, floor in MIN_PASSED_PER_FILE_E2E.items():
            got = by_file_passed.get(fname, 0)
            if got < floor:
                failures.append(f"{fname}: only {got} passed, floor is {floor}")
        by_title = {s["title"]: s for s in specs}
        for title in REQUIRED_PASSED_E2E:
            spec = by_title.get(title)
            if spec is None:
                failures.append(f"required real-login/discovery test missing from the report: {title!r}")
            elif spec["status"] != "expected":
                failures.append(f"required real-login/discovery test not passed ({spec['status']}): {title!r}")
        for s in skipped:
            if s["title"] != ALLOWED_SKIP_TITLE:
                failures.append(f"unexpected skip (only the documented cancel skip is allowed): "
                                f"{s['file']}: {s['title']!r}")
            else:
                notes.append(f"allowed skip kept: {s['file']}: {s['title']!r} ({ALLOWED_SKIP_REASON})")
    else:  # screenshots profile
        if total < MIN_TOTAL_SCREENSHOTS:
            failures.append(f"too few screenshot specs executed: total {total} < floor {MIN_TOTAL_SCREENSHOTS}")
        if passed != total:
            failures.append(f"screenshots run must pass every spec: passed {passed} of {total}")
        titles = [s["title"] for s in specs if s["status"] == "expected"]
        if not any(t.startswith("screenshots @ ") for t in titles):
            failures.append("no 'screenshots @ <viewport>' spec passed")
        if not any(t.startswith("settings + reset modal @ ") for t in titles):
            failures.append("no 'settings + reset modal @ <viewport>' spec passed")
        for s in skipped:
            failures.append(f"screenshots run must have zero skips, got skip: {s['file']}: {s['title']!r}")

    for s in failed:
        failures.append(f"failed spec: {s['file']}: {s['title']!r}")
    for s in flaky:
        failures.append(f"flaky spec (retries are 0, so this must not happen): {s['file']}: {s['title']!r}")
    for s in timed_out:
        failures.append(f"timed-out spec: {s['file']}: {s['title']!r}")

    if failures:
        print(f"PLAYWRIGHT_VALIDATOR: FAIL [{args.profile}] {summary} (target={got_target!r})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PLAYWRIGHT_VALIDATOR: PASS [{args.profile}] {summary} (target={got_target!r})")
    for n in notes:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
