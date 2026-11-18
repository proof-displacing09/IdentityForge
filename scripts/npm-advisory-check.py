#!/usr/bin/env python3
"""Fallback frontend advisory check via the GitHub Advisory Database.

Used ONLY when `npm audit` cannot run (e.g. the sandbox proxy blocks the
npm audit endpoint with 403 policy_denied). Queries the public GHSA API
for each direct dependency at its RESOLVED version from
frontend/package-lock.json (the `packages` section — the actual
resolved tree, not the minimal ranges in package.json) and reports
advisories affecting that version.

Exit codes: 0 = no high/critical advisory affects a pinned version;
1 = at least one high/critical advisory affects a pinned version;
2 = the advisory source could not be reached or its rate limit is
    exhausted (NOT RUN, never PASS). A partial result is never reported
    as clean.

Caching: a successful report younger than 24h that covers the current
pins is reused without new API calls (advisory data does not change
minute to minute; the cache lives in test-results/ and is NOT shipped
in the release ZIP, so a fresh extraction always checks live). A
PARTIAL report (some packages unreachable) is also cached: a retry
resumes it and only re-queries the missing packages, because the
shared unauthenticated quota is often exhausted mid-run. The
cache file records its timestamp and the pins it covers.

Coverage note (honest limitation): this checks DIRECT dependencies only
(`transitive_dependencies_examined: false` in the report). Transitive
advisories need `npm audit` on a machine with registry access; run that
there and record the result in docs/VERIFICATION_LOG.md. This script
must NEVER be used to satisfy the NPM_FULL_LOCKFILE_AUDIT gate — see
scripts/test-all.sh.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "frontend" / "package-lock.json"
OUT = ROOT / "test-results" / "audit-frontend-ghsa.json"
# Test seam (scripts/test-dependency-gates.sh): point the advisory
# source at a local stub server. Default is the real GitHub API;
# never set these in production use.
API = os.environ.get("IDENTITYFORGE_GHSA_API", "https://api.github.com/advisories")
RATE_LIMIT = os.environ.get(
    "IDENTITYFORGE_GHSA_RATE_LIMIT", "https://api.github.com/rate_limit")
CACHE_MAX_AGE_S = 24 * 3600
HEADERS = {"Accept": "application/vnd.github+json",
           "User-Agent": "IdentityForge-audit-check"}


def resolved_pins() -> dict[str, str]:
    """Direct dependencies at their RESOLVED versions.

    Direct = the root entry's dependencies + devDependencies in
    package-lock.json; resolved version = packages["node_modules/<name>"]
    ["version"] in the same lockfile (the actual installed tree, not
    the minimal ranges in package.json, which can resolve higher).
    Scoped packages live at node_modules/@scope/name.
    """
    lock = json.loads(LOCK.read_text())
    packages = lock.get("packages", {})
    root = packages.get("", {})
    names = list(root.get("dependencies", {})) + list(root.get("devDependencies", {}))
    pins: dict[str, str] = {}
    for name in sorted(names):
        entry = packages.get(f"node_modules/{name}", {})
        version = entry.get("version")
        if not version:
            raise ValueError(f"package-lock.json has no resolved version for {name}")
        pins[name] = version
    return pins


def get_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def main() -> int:
    pins = resolved_pins()
    checked_at = int(time.time())
    checked_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(checked_at))

    # Reuse a fresh cached report covering the same pins (0 API calls).
    if OUT.exists():
        try:
            cached = json.loads(OUT.read_text())
            age = time.time() - cached.get("checked_at_epoch", 0)
            if (age < CACHE_MAX_AGE_S
                    and cached.get("pins") == pins
                    and not cached.get("unreachable")):
                high = cached.get("high_critical_count", 0)
                print(f"GHSA check (cached {int(age // 60)}m ago, "
                      f"{cached.get('packages_checked')} direct packages): "
                      f"{high} high/critical affecting advisories. "
                      f"Report: {OUT}")
                return 1 if high else 0
        except (ValueError, OSError, KeyError):
            pass  # corrupt/old cache: fall through to a live check

    # Resume: reuse packages already checked successfully in a fresh
    # (<24h) partial report for the same pins — the shared
    # unauthenticated quota is often exhausted mid-run, so a retry must
    # only re-query what is still missing instead of starting over.
    done = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
            age = time.time() - prev.get("checked_at_epoch", 0)
            if age < CACHE_MAX_AGE_S and prev.get("pins") == pins:
                done = {r["package"]: r for r in prev.get("results", [])}
        except (ValueError, OSError, KeyError):
            done = {}
    todo = [(n, v) for n, v in pins.items() if n not in done]
    if todo:
        print(f"GHSA check: {len(done)} package(s) already checked in a "
              f"fresh partial report; querying {len(todo)} remaining.")

    # Pre-check the shared unauthenticated rate limit (60/hour per egress
    # IP) before spending requests on per-package queries. Only the
    # still-missing packages need quota.
    if todo:
        try:
            rl = get_json(RATE_LIMIT)
            remaining = rl["resources"]["core"]["remaining"]
            reset = rl["resources"]["core"]["reset"]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError,
                ValueError) as exc:
            print(f"GHSA check NOT RUN: rate-limit endpoint unreachable ({exc})")
            return 2
        if remaining < len(todo) + 1:
            when = time.strftime("%H:%M:%S UTC", time.gmtime(reset))
            print(f"GHSA check NOT RUN: GitHub API rate limit exhausted on "
                  f"the shared egress IP (remaining={remaining}, need "
                  f"{len(todo) + 1}, resets {when}). Retry after the reset "
                  f"or run `npm audit` on a machine with registry access.")
            return 2

    results = [done[n] for n in sorted(done)]
    unreachable = []
    for name, version in todo:
        query = urllib.parse.urlencode(
            {"ecosystem": "npm", "affects": f"{name}@{version}", "per_page": "100"})
        try:
            advisories = get_json(f"{API}?{query}")
            if isinstance(advisories, dict):  # error payload, not a list
                raise urllib.error.URLError(
                    f"unexpected response: {advisories.get('message')}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            unreachable.append({"package": name, "version": version,
                                "error": str(exc)})
            continue
        affecting = [
            {"ghsa_id": a.get("ghsa_id"), "cve_id": a.get("cve_id"),
             "severity": a.get("severity"),
             "summary": (a.get("summary") or "")[:200]}
            for a in advisories
        ]
        results.append({"package": name, "version": version,
                        "resolved_version": version,
                        "source": "GitHub Advisory Database "
                                  "(api.github.com/advisories)",
                        "advisories": affecting})
    results.sort(key=lambda r: r["package"])
    high = [r for r in results
            for a in r["advisories"]
            if a["severity"] in ("critical", "high")]
    report = {"source": "GitHub Advisory Database (api.github.com/advisories)",
              "coverage": "direct dependencies only; transitive advisories "
                          "require npm audit",
              "transitive_dependencies_examined": False,
              "checked_at_epoch": checked_at,
              "checked_at": checked_at_iso,
              "pins": pins,
              "packages_checked": len(results),
              "high_critical_count": len(high),
              "unreachable": unreachable,
              "results": results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")

    if unreachable:
        print(f"GHSA check INCOMPLETE: {len(unreachable)} package(s) "
              f"unreachable ({', '.join(u['package'] for u in unreachable)}) "
              f"— NOT RUN, see {OUT}")
        return 2
    if high:
        print(f"GHSA check FAILED: {len(high)} high/critical advisory(ies) "
              f"affect pinned versions:")
        for r in results:
            for a in r["advisories"]:
                if a["severity"] in ("critical", "high"):
                    print(f"  {r['package']}@{r['version']}: "
                          f"{a['severity']} {a['ghsa_id']} {a['cve_id']} — "
                          f"{a['summary']}")
        return 1
    total = sum(len(r["advisories"]) for r in results)
    print(f"GHSA check CLEAN: {len(results)} direct packages checked, "
          f"{total} affecting advisory(ies) at any severity, "
          f"0 at high/critical. Full report: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
