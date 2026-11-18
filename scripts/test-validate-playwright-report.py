#!/usr/bin/env python3
"""Self-test for scripts/validate-playwright-report.py (IF-V4-10, v5).

Builds Playwright JSON reports in the exact shape the real JSON
reporter emits (see frontend/test-results/playwright-report.json,
captured from a live 41-passed + 1-allowed-skip run) and asserts the
validator's verdict for each scenario. No live stack needed.

Scenarios:
  1. pass — full E2E report (portal 8, edge 9 with the one allowed
     skip, a11y 25), correct target -> rc 0
  2. unexpected-skip — an extra skipped spec ('deep link and
     refresh...') -> rc 1
  3. zero-real-login — the three real-login tests + discovery are
     absent (a run that never logged in) -> rc 1
  4. wrong-target — metadata.target is another project -> rc 1
  5. missing-report — no file at all -> rc 1
  6. stale-report — file mtime older than --since-epoch -> rc 1
  7. discovery-failed — the discovery-issuer test failed -> rc 1
  8. malformed-json — report is not JSON -> rc 1
  9. screenshots-pass — 24 screenshot specs, all passed -> rc 0
 10. screenshots-skip — one screenshot spec skipped -> rc 1
 11. e2e-report-as-screenshots — the E2E report validated with
     --profile screenshots must FAIL (wrong run for the profile)
 12. real-report — the captured live report (if present) validates
     PASS with its own target; skipped honestly when absent.

Usage: python3 scripts/test-validate-playwright-report.py
Exit 0 only when every scenario behaves as expected.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATOR = os.path.join(ROOT, "scripts", "validate-playwright-report.py")
TARGET = "identityforge-coldstart-20261111190000"

PASSED = 0
FAILED = 0


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"PASS: {name}")
    else:
        FAILED += 1
        print(f"FAIL: {name} {extra}")


def spec(title, status="expected", results=None):
    return {
        "title": title,
        "ok": status == "expected",
        "tests": [{
            "status": status,
            "results": [{"status": r} for r in (results or [status_to_result(status)])],
        }],
    }


def status_to_result(status):
    return {"expected": "passed", "skipped": "skipped",
            "unexpected": "failed", "flaky": "passed"}.get(status, "passed")


def file_suite(filename, describes):
    """describes: list of (describe title, [spec, ...])"""
    return {
        "title": filename,
        "file": filename,
        "specs": [],
        "suites": [
            {"title": dtitle, "file": filename, "specs": specs, "suites": []}
            for dtitle, specs in describes
        ],
    }


def report(suites, target=TARGET, base_url="http://127.0.0.1:5173"):
    return {
        "config": {"metadata": {"baseURL": base_url, "target": target}},
        "errors": [],
        "stats": {},
        "suites": suites,
    }


def e2e_suites(skip_extra=None, omit_login=False, discovery_status="expected"):
    portal = []
    if not omit_login:
        portal.append(spec("Keycloak discovery issuer is the pinned canonical issuer",
                           status=discovery_status))
        portal.append(spec("student_01: member 200, officer 403"))
        portal.append(spec("logout revokes the session; stale cookie is denied (401)"))
        portal.append(spec("officer_01: member 200 and officer 200"))
        portal.append(spec("deep link and refresh keep the portal view and session",
                           status="skipped" if skip_extra == "deep-link" else "expected"))
        portal.append(spec("callback error path shows a safe reason, no session"))
        portal.append(spec("logout without a CSRF token is rejected 403 and the session survives"))
        portal.append(spec("unknown route renders the 404 view"))
    else:
        portal = [spec(f"portal filler {i}") for i in range(8)]
    edge = [
        spec("menu button controls the sidebar nav; Escape closes and focus returns"),
        spec("provider error callback shows a safe reason, no session"),
        spec("user cancels at the Keycloak login page", status="skipped"),
        spec("browser back after logout shows the signed-out portal"),
        spec("unknown state at the callback is rejected (STATE_REUSED)"),
        spec("missing state parameter is rejected (CALLBACK_MALFORMED)"),
        spec("empty state is rejected (STATE_MISSING)"),
        spec("second callback replay is rejected (STATE_REUSED)"),
        spec("CSV is labelled CLIENT-DERIVED and JSON is a server artifact"),
    ]
    a11y = [spec(f"axe view {i}") for i in range(25)]
    return [
        file_suite("portal.spec.ts", [("real Keycloak login", portal)]),
        file_suite("edge.spec.ts", [("login edge cases", edge)]),
        file_suite("a11y.spec.ts", [("axe scans — all views", a11y)]),
    ]


def screenshots_suites(skipped_title=None):
    specs = []
    for vp in ["320x740", "390x844", "768x1024", "1280x800", "1440x900", "1920x1080"]:
        specs.append(spec(f"screenshots @ {vp}"))
        specs.append(spec(f"settings + reset modal @ {vp}"))
    for title in ["findings empty state (fresh browser, no runs)",
                  "overview loading state (status delayed)",
                  "overview error state (status 500)",
                  "portal access-denied state (student loads officer resource)",
                  "overview provider-down state (IdP unreachable, honest not-ready)",
                  "overview wrong-issuer state (reachable, issuer mismatch — never Verified)",
                  "overview not-run state (no verified login, no live logins)",
                  "settings identity-unknown state (/portal/me returns 500)",
                  "200% zoom layout equivalent (720 CSS px viewport)",
                  "400% zoom layout equivalent (360 CSS px viewport)",
                  "increased text size (root font-size 125%)",
                  "forced colours (high-contrast) overview"]:
        specs.append(spec(title, status="skipped" if title == skipped_title else "expected"))
    return [file_suite("screenshots.spec.ts", [("screenshots", specs)])]


def run_validator(path, profile="e2e", target=TARGET, since=0):
    cmd = [sys.executable, VALIDATOR, "--report", path,
           "--target", target, "--profile", profile]
    if since:
        cmd += ["--since-epoch", str(since)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        def write(name, data):
            p = os.path.join(tmp, name)
            if isinstance(data, str):
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(data)
            else:
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(data, fh)
            return p

        # 1. pass
        p = write("pass.json", report(e2e_suites()))
        rc, out = run_validator(p)
        check("1 full E2E report with correct target -> PASS (rc 0)",
              rc == 0 and "PASS [e2e]" in out and "total=42" in out and "passed=41" in out, out)

        # 2. unexpected skip
        p = write("skip.json", report(e2e_suites(skip_extra="deep-link")))
        rc, out = run_validator(p)
        check("2 extra skipped spec -> FAIL (rc 1, names the spec)",
              rc == 1 and "unexpected skip" in out and "deep link" in out, out)

        # 3. zero real-login assertions
        p = write("nologin.json", report(e2e_suites(omit_login=True)))
        rc, out = run_validator(p)
        check("3 report without the real-login tests -> FAIL (rc 1)",
              rc == 1 and "required real-login/discovery test missing" in out, out)

        # 4. wrong target
        p = write("wrongtarget.json", report(e2e_suites(), target="identityforge-coldstart-OTHER"))
        rc, out = run_validator(p)
        check("4 report for another project -> FAIL (rc 1, target mismatch)",
              rc == 1 and "target mismatch" in out, out)

        # 5. missing report
        rc, out = run_validator(os.path.join(tmp, "does-not-exist.json"))
        check("5 missing report file -> FAIL (rc 1)",
              rc == 1 and "report missing" in out, out)

        # 6. stale report
        p = write("stale.json", report(e2e_suites()))
        old = time.time() - 3600
        os.utime(p, (old, old))
        rc, out = run_validator(p, since=time.time() - 60)
        check("6 stale report (mtime before run start) -> FAIL (rc 1)",
              rc == 1 and "stale" in out, out)

        # 7. discovery failed
        p = write("discfail.json", report(e2e_suites(discovery_status="unexpected")))
        rc, out = run_validator(p)
        check("7 discovery-issuer test failed -> FAIL (rc 1)",
              rc == 1 and "discovery issuer" in out and "not passed" in out, out)

        # 8. malformed JSON
        p = write("malformed.json", "this is not json {")
        rc, out = run_validator(p)
        check("8 malformed JSON report -> FAIL (rc 1)",
              rc == 1 and "not valid JSON" in out, out)

        # 9. screenshots pass
        p = write("shots.json", report(screenshots_suites()))
        rc, out = run_validator(p, profile="screenshots")
        check("9 screenshots report, all 24 passed -> PASS (rc 0)",
              rc == 0 and "PASS [screenshots]" in out and "total=24" in out, out)

        # 10. screenshots skip
        p = write("shotsskip.json", report(screenshots_suites(
            skipped_title="overview error state (status 500)")))
        rc, out = run_validator(p, profile="screenshots")
        check("10 screenshots report with one skip -> FAIL (rc 1)",
              rc == 1 and "zero skips" in out, out)

        # 11. E2E report validated as screenshots must fail
        p = write("e2e-as-shots.json", report(e2e_suites()))
        rc, out = run_validator(p, profile="screenshots")
        check("11 E2E report under the screenshots profile -> FAIL (rc 1)",
              rc == 1, out)

        # 12. real captured report (if present) validates PASS
        real = os.path.join(ROOT, "frontend", "test-results", "playwright-report.json")
        if os.path.isfile(real):
            with open(real, encoding="utf-8") as fh:
                target = json.load(fh)["config"]["metadata"]["target"]
            rc, out = run_validator(real, target=target)
            check(f"12 captured live report validates PASS (target={target})",
                  rc == 0 and "PASS [e2e]" in out, out)
        else:
            print("SKIP: 12 captured live report absent (no live E2E run in this tree)")

    print(f"\ntest-validate-playwright-report: {PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
