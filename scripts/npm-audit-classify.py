#!/usr/bin/env python3
"""Classify an `npm audit --json` result (IF-V4-09, v5).

`npm audit` exit code 1 is AMBIGUOUS: it means "vulnerabilities
found" but also "the audit endpoint errored". A blocked registry,
a DNS failure, a proxy 403, a 429, a timeout, or malformed output
must never be reported as (or mistaken for) a vulnerability finding —
and a real finding must never be hidden behind a NOT RUN. This
classifier reads the JSON audit report (stdout) plus the stderr
text, and distinguishes:

  CLEAN                 JSON metadata, 0 high/critical vulnerabilities
  VULNERABILITIES_FOUND JSON metadata, >= 1 high/critical vulnerability
  NOT_RUN:<reason>      BLOCKED (403/policy_denied), DNS, TIMEOUT,
                        RATE_LIMIT (429), OFFLINE, REGISTRY_ERROR
  CHECK_FAILED          malformed JSON, missing metadata, unknown
                        error code, or an rc that contradicts the
                        report (e.g. rc=0 with high>0)

Exit codes: 0 = CLEAN, 1 = VULNERABILITIES_FOUND,
2 = NOT RUN (any reason), 3 = CHECK_FAILED.
Prints one machine-readable line: STATUS=<classification> <reason>
(plus advisory names for findings). Callers map 2/3 to the gate
status NOT RUN with the reason in the gate detail; only 0 and 1
mean the audit actually executed.

Usage: npm-audit-classify.py <audit-stdout-log> [--stderr <file>]
         [--rc <npm-exit-code>]
"""
import json
import re
import sys
from pathlib import Path

BLOCKED_MARKERS = (
    "policy_denied",
    "403 Forbidden",
    "audit endpoint returned an error",
    "E403",
)
DNS_MARKERS = ("ENOTFOUND", "EAI_AGAIN", "getaddrinfo", "EAI_NODATA")
TIMEOUT_MARKERS = ("ETIMEDOUT", "ESOCKETTIMEDOUT", "network timeout",
                   "timed out", "Timeout")
RATE_MARKERS = ("E429", "429 Too Many Requests", "rate limit")
OFFLINE_MARKERS = ("ECONNREFUSED", "ENETUNREACH", "EOFFLINE",
                   "offline", "network is unreachable")


def classify_text(text):
    """Fallback classification from combined stdout+stderr text."""
    for marker in BLOCKED_MARKERS:
        if marker in text:
            return ("NOT_RUN:BLOCKED", f"npm audit endpoint blocked ({marker})")
    for marker in DNS_MARKERS:
        if marker in text:
            return ("NOT_RUN:DNS", f"npm audit DNS failure ({marker})")
    for marker in RATE_MARKERS:
        if marker in text:
            return ("NOT_RUN:RATE_LIMIT", f"npm audit rate-limited ({marker})")
    for marker in TIMEOUT_MARKERS:
        if marker in text:
            return ("NOT_RUN:TIMEOUT", f"npm audit timed out ({marker})")
    for marker in OFFLINE_MARKERS:
        if marker in text:
            return ("NOT_RUN:OFFLINE", f"npm audit could not reach the registry ({marker})")
    # npm text report: "N vulnerabilities (1 low, 1 high, ...)"
    m = re.search(r"(\d+) vulnerabilities?\s*\(([^)]*)\)", text)
    if m:
        counts = {sev: int(num) for num, sev in
                  re.findall(r"(\d+)\s+(low|moderate|high|critical)", m.group(2))}
        high = counts.get("high", 0) + counts.get("critical", 0)
        if high > 0:
            return ("VULNERABILITIES_FOUND",
                    f"text audit report: {m.group(0)}")
        return ("CLEAN", f"text audit report: {m.group(0)}")
    return (None, "")


def main(argv):
    args = list(argv)
    rc = None
    stderr_file = None
    log_file = None
    i = 0
    while i < len(args):
        if args[i] == "--rc" and i + 1 < len(args):
            rc = int(args[i + 1])
            i += 2
        elif args[i] == "--stderr" and i + 1 < len(args):
            stderr_file = args[i + 1]
            i += 2
        elif args[i].startswith("--"):
            print(f"npm-audit-classify: unknown option {args[i]}", file=sys.stderr)
            return 2
        else:
            log_file = args[i]
            i += 1
    if log_file is None:
        print("usage: npm-audit-classify.py <audit-stdout-log> [--stderr <file>] [--rc N]",
              file=sys.stderr)
        return 2

    stdout_text = Path(log_file).read_text(errors="replace") if Path(log_file).exists() else ""
    stderr_text = ""
    if stderr_file and Path(stderr_file).exists():
        stderr_text = Path(stderr_file).read_text(errors="replace")
    combined = stdout_text + "\n" + stderr_text

    if rc == 124:
        print("STATUS=NOT_RUN:TIMEOUT npm audit timed out (rc=124, 120s bound)")
        return 2

    # --- JSON path (the normal case: `npm audit --json`) -----------------
    try:
        data = json.loads(stdout_text)
    except json.JSONDecodeError:
        status, reason = classify_text(combined)
        if status:
            print(f"STATUS={status} {reason}")
            return 1 if status == "VULNERABILITIES_FOUND" else (0 if status == "CLEAN" else 2)
        print(f"STATUS=CHECK_FAILED npm audit output was not valid JSON (rc={rc}); "
              f"cannot confirm findings or cleanliness")
        return 3

    if isinstance(data, dict) and "error" in data:
        err = data["error"] or {}
        code = str(err.get("code", ""))
        detail = " ".join(
            str(err.get("detail", "") or err.get("summary", "") or code).split())
        text = code + " " + detail + " " + combined
        status, reason = classify_text(text)
        if status and status.startswith("NOT_RUN"):
            print(f"STATUS={status} npm audit error {code}: {detail}")
            return 2
        print(f"STATUS=CHECK_FAILED npm audit returned error {code}: {detail}")
        return 3

    metadata = data.get("metadata") if isinstance(data, dict) else None
    if not isinstance(metadata, dict) or "vulnerabilities" not in metadata:
        print("STATUS=CHECK_FAILED npm audit JSON has no metadata.vulnerabilities; "
              "cannot confirm findings or cleanliness")
        return 3
    vulns = metadata["vulnerabilities"] or {}
    try:
        high = int(vulns.get("high", 0))
        critical = int(vulns.get("critical", 0))
    except (TypeError, ValueError):
        print("STATUS=CHECK_FAILED metadata.vulnerabilities counts are not integers")
        return 3
    if high + critical > 0:
        names = []
        advisories = data.get("advisories") or data.get("vulnerabilities") or {}
        if isinstance(advisories, dict):
            for key, adv in list(advisories.items())[:5]:
                if isinstance(adv, dict):
                    names.append(str(adv.get("module_name") or adv.get("name") or key))
        if rc == 0:
            print("STATUS=CHECK_FAILED npm audit rc=0 but metadata reports "
                  f"{high} high + {critical} critical vulnerabilities — contradictory report")
            return 3
        print(f"STATUS=VULNERABILITIES_FOUND npm audit found {high} high + "
              f"{critical} critical vulnerabilities"
              + (f" (e.g. {', '.join(names)})" if names else ""))
        return 1
    if rc == 1:
        print("STATUS=CHECK_FAILED npm audit rc=1 but metadata reports 0 high/critical "
              "vulnerabilities — contradictory report")
        return 3
    total = vulns.get("total", "?")
    print(f"STATUS=CLEAN npm audit clean at --audit-level=high "
          f"(metadata total={total}, 0 high/critical)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
