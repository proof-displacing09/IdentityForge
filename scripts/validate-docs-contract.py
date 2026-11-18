#!/usr/bin/env python3
"""Docs-contract validation (Trustline v5, IF-V4-06).

Every reason code and run-report field named in the docs, example
reports, and UI copy must be exactly the value/field the source
defines. Stale codes (AUDIENCE_MISMATCH, PKCE_VERIFIER_MISMATCH, ...)
and invented report keys (flawed_fixture_result) are drift, and this
script fails on drift so CI catches it before a release does.

Authoritative sources -- parsed from the tree, never hardcoded:
  * FailureReason enum values -- backend/src/identityforge/models.py
    (or <root>/src/identityforge/models.py inside the test container,
    where the backend image lays the package out as /app/src).
  * Run-report model fields -- ComparisonResult, TransactionStep,
    ValidationCheck, ReproducibilityMetadata, EvidenceArtifact and
    Finding in the same file.

Checks:
  1. DENYLIST -- retired reason codes / report keys must not appear in
     current-guidance files (docs that instruct, example reports, UI
     copy). History files (REMEDIATION_FINDINGS.md,
     REMEDIATION_TRACEABILITY.md, VERIFICATION_LOG.md,
     RELEASE_MANIFEST.md) may name retired codes in PLAIN prose when
     describing what was wrong -- never in backticks, never as current
     guidance -- so the denylist does not apply to them; the backticked
     token check below still does.
  2. BACKTICKED TOKENS -- every `UPPER_SNAKE` token in a scanned file
     must be a FailureReason value or a constant that exists in the
     source tree (harvested from string literals / identifiers) or in
     the small curated allowlist below. A token that is none of those
     is either a stale reason code or an undocumented constant.
  3. REPORT FIELDS -- backticked `snake_case` tokens from the report
     family (secure_*, flawed_*, validation_*, resource_access*,
     observed_*, expected_*, evidence_*, session_preexisted,
     session_revoked, protected_resource*, timeline, decisions, ...)
     must be fields of the report models (or `evidence_hash`, the
     stored-report hash named in docs/API_CONTRACT.md section 6).
  4. EXAMPLE JSON -- single-run report JSON (files whose top-level
     object carries `scenario_id`) must use only model fields as keys
     (plus `evidence_hash`), and every reason-code value
     (secure_reason, flawed_reason, timeline[].reason_code,
     decisions[].reason_code) must be a FailureReason value.
  5. QUICKSTART ARCHIVE NAMES (IF-V7.1-05, v7.2) -- the archive-hash
     commands in the CURRENT quickstart sections (REVIEWER_GUIDE.md
     section 0, WINDOWS_SETUP.md section 3) must name the released
     final archive -- the **Filename:** of the LAST "Operation
     Trustline" section in docs/RELEASE_MANIFEST.md -- or an explicit
     variable ($ZIP). A stale candidate name (any *CANDIDATE archive,
     e.g. the v6 REVIEW_CANDIDATE name), or a different
     concrete filename, is drift. Historical narrative sections may
     still name old archives as history; only the quickstart regions
     are checked, never the history files.
  6. STALE RELEASE PROSE (IF-V8-80, WS3, v8) -- the same two guides
     must not name an OLDER release in prose the existing checks do
     not cover: (6a) any release label (`v7.3`, `TRUSTLINE_V7.3.1`,
     ...) in a quickstart region that is not the current release
     label from the manifest's last Trustline section (finding IDs
     such as IF-V7.1-05 and `.zip` command lines, which check 5
     owns, are excluded); (6b) any "release version X.Y.Z" prose in
     either guide must equal the manifest's current **Version:**.
     Historical 1.7.3 mentions live in RELEASE_MANIFEST.md and
     VERIFICATION_LOG.md history sections, which this rule does not
     scan -- the two guides carry no history sections, so any
     "release version" there is current guidance, never history.
  7. STALE ACTIVE COUNTS (v8.0.1, WS1) -- the README's ACTIVE test
     prose must agree with the current release: (7a) any pytest
     count in the `## Tests` section ("(482 tests") must equal the
     backend-pytest count in the manifest's last Trustline section
     `**Counts (current release):**` line; (7b) the "**N explicit
     gates**" sentence in the same section must agree with the gate
     IDs it lists AND with the gate IDs the runners define
     (`scripts/test-all.sh` + `scripts/audit-gates.sh` call sites),
     which must also agree with the counts line's gate number. Only
     the `## Tests` region is scanned: the README's dated release
     history below it legitimately names old counts (340/397/482 in
     historical context), and a count that is absent is not flagged
     -- only a present count that disagrees is drift.

Usage:
  python3 scripts/validate-docs-contract.py [--root DIR]
      [--scan PATH ...]   paths relative to root; default: the full
                          normative tree (docs, README.md, SECURITY.md,
                          example-reports, frontend/src, scripts/*.md)
  Exit 0 = contract holds; 1 = drift found; 2 = usage/source error.
  Stdlib only; no network, no Docker, no venv needed.

  IF-V5-01 (v6): path independence. The source-token harvest filters
  on path components RELATIVE TO THE PROJECT ROOT (resolved paths,
  p.relative_to(root)), never on absolute p.parts: an ancestor
  directory named `data`, `scripts`, `node_modules` or `test-results`
  must not change the result. Exclusions for `backend/data`,
  `test-results`, `node_modules`, caches and generated files apply
  only BELOW the root. A harvested file that resolves outside the
  root (symlink escape) is skipped, never followed. The gate fails
  (exit 2) if it harvests zero source files or scans zero files —
  a green gate on an empty scan is a silent pass, not a proof.
  Regression: scripts/test-docs-contract-paths.sh (normal path,
  `data/` ancestor, path with spaces; stale-code, below-root
  exclusion, symlink-escape and empty-scan negatives).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# Retired codes / keys. These strings must not appear in current-guidance
# files at all -- not even in a "for example" table. History files may
# name them in plain prose (see module docstring); the script itself is
# excluded from scanning because it has to list them here.
DENYLIST = (
    "AUDIENCE_MISMATCH",
    "PKCE_VERIFIER_MISMATCH",
    "ISSUER_MISMATCH",
    "TOKEN_EXPIRED",
    "TRANSACTION_REPLAYED",
    "INVALID_SIGNATURE",
    "ALGORITHM_NOT_ALLOWED",
    "MISSING_TOKEN",
    "CSRF_CHECK_FAILED",
    "INPUT_TOO_LARGE",
    "ISSUER_NOT_ALLOWLISTED",
    "flawed_fixture_result",
)

# History files: append-only records of past releases. They may describe
# retired codes in plain prose; the denylist does not apply to them.
HISTORY_FILES = {
    "docs/REMEDIATION_FINDINGS.md",
    "docs/REMEDIATION_TRACEABILITY.md",
    "docs/VERIFICATION_LOG.md",
    "docs/RELEASE_MANIFEST.md",
}

# Backticked UPPER_SNAKE tokens that are real, documented constants but
# do not appear as string literals / identifiers anywhere in the source
# tree. Each entry carries its source so a reviewer can check it.
# Everything else must be a FailureReason value or harvested from source.
CURATED_ALLOWLIST = {
    # Fragments of a wrapped `WRONG_AUDIENCE` code (REMEDIATION_FINDINGS
    # P2-20: reason codes render with <wbr/> after each underscore).
    "WRONG_": "fragment of WRONG_AUDIENCE split across a line break",
    "AUDIENCE": "fragment of WRONG_AUDIENCE split across a line break",
    # Keycloak probe echo text (docs/REVIEWER_GUIDE.md section 7).
    "HEALTHCHECK_OK": "echo text of the in-image healthcheck probe",
    # Deprecated Keycloak option name, documented as history
    # (docs/AUTH_FLOW.md section 6).
    "KC_HOSTNAME_PORT": "removed Keycloak hostname option, named as history",
    # Docker Desktop managed-distro note (docs/WINDOWS_SETUP.md).
    "NO_PROXY": "environment variable name",
    "HTTP_PROXY": "environment variable name",
    # Template placeholder marker (example-reports/REPORT_TEMPLATE.json).
    "TEMPLATE": "placeholder marker in the report template",
    # The docs-contract script's own allowlist identifiers, named in
    # docs/REMEDIATION_FINDINGS.md (v5, IF-V4-06 own-goal note).
    "FIELD_ALLOWLIST": "identifier in scripts/validate-docs-contract.py",
    "CURATED_ALLOWLIST": "identifier in scripts/validate-docs-contract.py",
    # Readiness pill labels (frontend/src/App.tsx renders them as
    # lower-case prose; the docs quote them in upper case).
    "READY": "readiness label quoted in docs",
    "NOT_FOUND": "HTTP 404 detail string",
    # Status words (README.md status table) -- not reason codes.
    "BLOCKED": "status word in the README status table",
    # PKCE / JWT algorithm labels quoted in docs.
    "S256": "PKCE code-challenge method (RFC 7636)",
    "RS256": "JWT signing algorithm (RFC 7518)",
    "HS256": "JWT signing algorithm (RFC 7518)",
}

# Real snake_case fields that look like run-report fields but belong to
# a different API object. Each entry carries its source.
FIELD_ALLOWLIST = {
    # Key of the lab/status `evidence` object (backend/src/identityforge/
    # api/app.py:355; frontend/src/types.ts:116) -- not a run-report field.
    "evidence_available": "lab/status evidence object",
    # Scenario-definition field in the frontend contract
    # (frontend/src/types.ts:76; the backend model field is
    # `expected_secure` in ScenarioDefinition).
    "expected_secure_result": "scenario definition, frontend contract",
}

# Report-family prefixes: backticked snake_case tokens starting with one
# of these must be a field of the report models (or evidence_hash).
REPORT_FIELD_PREFIXES = (
    "secure_",
    "flawed_",
    "validation_",
    "resource_access",
    "observed_",
    "expected_",
    "evidence_",
    "session_preexisted",
    "session_revoked",
    "protected_resource",
    "transaction_timeline",
    "verifier_decisions",
    "blocked_reason",
    "observed_outcome",
)

# JSON keys that are legitimate in a single-run report but are not model
# fields (documented in docs/API_CONTRACT.md section 6).
JSON_KEY_ALLOWLIST = {"evidence_hash"}

# Reason-code value fields in example JSON (dotted path inside the run
# object; "*" walks a list).
REASON_VALUE_PATHS = (
    "secure_reason",
    "flawed_reason",
    "timeline.*.reason_code",
    "decisions.*.reason_code",
)

# Check 5 (IF-V7.1-05, v7.2): current quickstart sections whose
# archive-hash commands must name the released final archive.
# Keyed by BASENAME so the rule applies wherever the file is scanned
# from; the value is the heading that opens the quickstart region
# (the region ends at the next "## " heading). Historical narrative
# sections of the same files are NOT in these regions and are never
# checked here.
QUICKSTART_REGIONS = {
    "REVIEWER_GUIDE.md": "## 0.",
    "WINDOWS_SETUP.md": "## 3.",
}
ZIP_NAME_RE = re.compile(r"[\w.\-]+\.zip")
MANIFEST_FILENAME_RE = re.compile(r"\*\*Filename:\*\*\s*`([^`]+)`")


def read_current_archive_filename(root: Path) -> str:
    """The **Filename:** of the LAST Operation Trustline section.

    The release manifest is append-only history: the last Trustline
    section is the current release, and its Filename is the archive
    the quickstart commands must name.
    """
    text = (root / "docs" / "RELEASE_MANIFEST.md").read_text(encoding="utf-8")
    sections = list(re.finditer(r"^## Operation Trustline.*$", text, re.MULTILINE))
    if not sections:
        raise ValueError(
            "docs/RELEASE_MANIFEST.md has no '## Operation Trustline' section"
        )
    current = text[sections[-1].start():]
    match = MANIFEST_FILENAME_RE.search(current)
    if not match:
        raise ValueError(
            "the last '## Operation Trustline' section in "
            "docs/RELEASE_MANIFEST.md has no '**Filename:** `...zip`' line"
        )
    return match.group(1)


def quickstart_region_lines(text: str, start_heading: str) -> list[tuple[int, str]]:
    """(lineno, line) pairs inside the quickstart region of a file.

    From the heading starting with `start_heading` to (not including)
    the next line starting with "## ". Empty when the heading is absent.
    """
    lines = text.splitlines()
    in_region = False
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if line.startswith("## "):
            if in_region:
                break
            if line.startswith(start_heading):
                in_region = True
            continue
        if in_region:
            found.append((lineno, line))
    return found


RELEASE_LABEL_RE = re.compile(r"\bv(\d+(?:\.\d+)*)\b", re.IGNORECASE)
TRUSTLINE_LABEL_RE = re.compile(r"TRUSTLINE_V([\w.]+)", re.IGNORECASE)
RELEASE_VERSION_PROSE_RE = re.compile(
    r"release version\s+(\d+\.\d+\.\d+)", re.IGNORECASE
)
MANIFEST_VERSION_RE = re.compile(r"\*\*Version:\*\*\s*(\d+\.\d+\.\d+)")
MANIFEST_LABEL_RE = re.compile(r"^## Operation Trustline\s+(v[\w.]+)\b", re.IGNORECASE)

# Check 7 (v8.0.1, WS1): active README counts. The manifest's last
# Trustline section carries one machine-readable counts line; the
# runners carry the gate IDs as call sites.
MANIFEST_COUNTS_RE = re.compile(
    r"\*\*Counts \(current release\):\*\*\s*backend pytest\s+(\d+);"
    r"\s*test-all gates\s+(\d+)"
)
GATE_CALL_RE = re.compile(
    r"^\s*(?:gate|skip_gate|na_gate)\s+([A-Z][A-Z0-9_]+)\b", re.MULTILINE
)
GATE_RUNNER_FILES = ("scripts/test-all.sh", "scripts/audit-gates.sh")
PYTEST_COUNT_RE = re.compile(r"pytest[^\n]*\(\s*(\d+)\s+tests\b")
EXPLICIT_GATES_RE = re.compile(r"\*\*(\d+) explicit gates\*\*")
GATE_ID_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")


def read_current_counts(root: Path) -> tuple[int, int]:
    """(pytest count, gate count) of the LAST Operation Trustline section.

    Parsed from that section's `**Counts (current release):**` line
    (e.g. "backend pytest 482; test-all gates 18"). Raises ValueError
    when the line is absent -- a release record without stated counts
    cannot anchor the README check, and the gate must fail loudly
    (exit 2) rather than pass a README it could not compare.
    """
    text = (root / "docs" / "RELEASE_MANIFEST.md").read_text(encoding="utf-8")
    sections = list(re.finditer(r"^## Operation Trustline.*$", text, re.MULTILINE))
    if not sections:
        raise ValueError(
            "docs/RELEASE_MANIFEST.md has no '## Operation Trustline' section"
        )
    current = text[sections[-1].start():]
    match = MANIFEST_COUNTS_RE.search(current)
    if not match:
        raise ValueError(
            "the last '## Operation Trustline' section in "
            "docs/RELEASE_MANIFEST.md has no "
            "'**Counts (current release):** backend pytest N; "
            "test-all gates M' line"
        )
    return int(match.group(1)), int(match.group(2))


def read_runner_gate_ids(root: Path) -> set[str]:
    """Distinct gate IDs the runners define (test-all.sh + audit-gates.sh).

    A gate exists because a runner records it: every `gate` /
    `skip_gate` / `na_gate` call site contributes its ID, so the
    dependency gates (recorded by audit-gates.sh, sourced by
    test-all.sh) count alongside the direct call sites. Raises
    ValueError when a runner file is missing -- the gate count then
    has no code ground truth to compare against.
    """
    ids: set[str] = set()
    for rel in GATE_RUNNER_FILES:
        path = root / rel
        if not path.is_file():
            raise ValueError(f"gate runner file missing: {rel}")
        ids.update(GATE_CALL_RE.findall(path.read_text(encoding="utf-8")))
    if not ids:
        raise ValueError("no gate call sites found in the runner files")
    return ids


def tests_region_lines(text: str) -> list[tuple[int, str]]:
    """(lineno, line) pairs inside README.md's `## Tests` section.

    From the "## Tests" heading to (not including) the next "## "
    heading. The dated release history below it is NOT in this region
    and is never checked here.
    """
    lines = text.splitlines()
    in_region = False
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        if line.startswith("## "):
            if in_region:
                break
            if line.startswith("## Tests"):
                in_region = True
            continue
        if in_region:
            found.append((lineno, line))
    return found


def check_active_counts(root: Path, files: list[Path], violations: list[str]) -> None:
    """Check 7: README active test/gate counts must match the current release.

    (7a) A pytest count in the `## Tests` section must equal the
    backend-pytest count in the manifest's counts line. (7b) The
    "**N explicit gates**" sentence in the same section must agree
    with the gate IDs it lists, with the counts line's gate number,
    and with the gate IDs the runners define. Only present counts are
    compared -- an absent count is not drift, and history sections
    are never scanned.
    """
    # Prefer the README at the project root: the scan also collects
    # docs/pentest-evidence/README.md and example-reports/README.md,
    # and a first-match-by-name pick would silently check one of
    # those (no "## Tests" region -> early return -> stale active
    # counts pass). Fall back to the first scanned README.md so the
    # paths-suite fixtures (which scan a single planted README under
    # a subdirectory) keep working.
    readmes = [p for p in files if p.name == "README.md"]
    if not readmes:
        return
    root_readme = (root / "README.md").resolve()
    readme = next(
        (p for p in readmes if p.resolve() == root_readme), readmes[0]
    )
    rel = str(readme.relative_to(root))
    text = readme.read_text(encoding="utf-8", errors="ignore")
    region = tests_region_lines(text)
    if not region:
        return
    expected_pytest, expected_gates = read_current_counts(root)
    runner_ids = read_runner_gate_ids(root)
    if len(runner_ids) != expected_gates:
        violations.append(
            f"{rel}: the manifest counts line says {expected_gates} "
            f"test-all gates, but the runners define "
            f"{len(runner_ids)} gate IDs "
            f"({', '.join(sorted(runner_ids))}) -- fix the counts "
            f"line or the runners"
        )
    region_text = "\n".join(line for _, line in region)
    for lineno, line in region:
        for match in PYTEST_COUNT_RE.finditer(line):
            if int(match.group(1)) != expected_pytest:
                violations.append(
                    f"{rel}:{lineno}: active test prose says "
                    f"({match.group(1)} tests, but the current release "
                    f"runs {expected_pytest} backend tests "
                    f"(docs/RELEASE_MANIFEST.md counts line) -- "
                    f"update the prose"
                )
    gates_match = EXPLICIT_GATES_RE.search(region_text)
    if gates_match:
        stated = int(gates_match.group(1))
        after = region_text[gates_match.end():]
        colon = after.find(":")
        listed: list[str] = []
        if colon != -1:
            listed_span = after[colon + 1:].split(".", 1)[0]
            listed = GATE_ID_TOKEN_RE.findall(listed_span)
        if stated != len(listed):
            violations.append(
                f"{rel}: active gate prose says **{stated} explicit "
                f"gates** but lists {len(listed)} gate IDs -- fix the "
                f"number or the list"
            )
        if stated != expected_gates:
            violations.append(
                f"{rel}: active gate prose says **{stated} explicit "
                f"gates**, but the current release defines "
                f"{expected_gates} "
                f"(docs/RELEASE_MANIFEST.md counts line) -- update "
                f"the prose"
            )
        if set(listed) != runner_ids:
            missing = sorted(runner_ids - set(listed))
            extra = sorted(set(listed) - runner_ids)
            detail = []
            if missing:
                detail.append(f"missing from the list: {', '.join(missing)}")
            if extra:
                detail.append(f"not runner gates: {', '.join(extra)}")
            violations.append(
                f"{rel}: the listed gate IDs disagree with the "
                f"runners ({'; '.join(detail)}) -- update the list"
            )


def read_current_release(root: Path) -> tuple[str, str]:
    """(label, version) of the LAST Operation Trustline manifest section.

    Label is the release label from the section heading (e.g. "v8");
    version is that section's **Version:** line. Raises ValueError
    when either cannot be read (a source error, exit 2).
    """
    text = (root / "docs" / "RELEASE_MANIFEST.md").read_text(encoding="utf-8")
    sections = list(re.finditer(r"^## Operation Trustline.*$", text, re.MULTILINE))
    if not sections:
        raise ValueError(
            "docs/RELEASE_MANIFEST.md has no '## Operation Trustline' section"
        )
    current = text[sections[-1].start():]
    label_match = MANIFEST_LABEL_RE.search(current)
    version_match = MANIFEST_VERSION_RE.search(current)
    if not label_match or not version_match:
        raise ValueError(
            "the last '## Operation Trustline' section in "
            "docs/RELEASE_MANIFEST.md has no release label or "
            "'**Version:** X.Y.Z' line"
        )
    return label_match.group(1).lower(), version_match.group(1)


def check_stale_release_prose(root: Path, files: list[Path], violations: list[str]) -> None:
    """Check 6: quickstart/hash-check prose must not name an older release.

    (6a) Any release label in a quickstart region that is not the
    current release label is drift. Finding IDs (IF-V7.1-05) and
    `.zip` command lines (check 5's territory) are excluded so this
    check cannot double-flag or misread them. The label search is
    scoped to lines that describe the release itself ("final
    release"): in-region history notes such as "(v7.3)" or
    "re-measured in the v7.1 battery" legitimately name older
    releases and are NOT flagged. (6b) Any "release version X.Y.Z"
    prose in either guide must equal the manifest's current version.
    The two guides carry no history sections, so every "release
    version" there is current guidance.
    """
    label, version = read_current_release(root)
    for path in files:
        if path.name not in QUICKSTART_REGIONS:
            continue
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in quickstart_region_lines(
            text, QUICKSTART_REGIONS[path.name]
        ):
            if ".zip" in line or "final release" not in line.lower():
                continue  # check 5 owns archive-command lines; other
                # in-region lines may legitimately name older releases
                # as history (e.g. "(v7.3)", "v7.1 battery")
            for match in RELEASE_LABEL_RE.finditer(line):
                before = line[max(0, match.start() - 3):match.start()]
                if before.upper().endswith("IF-"):
                    continue  # finding ID, e.g. IF-V7.1-05
                if match.group(0).lower() != label:
                    violations.append(
                        f"{rel}:{lineno}: quickstart prose names an older "
                        f"release label `{match.group(0)}`, but the current "
                        f"release is `{label}` "
                        f"(docs/RELEASE_MANIFEST.md) — update the prose"
                    )
            for match in TRUSTLINE_LABEL_RE.finditer(line):
                if match.group(0).upper() != f"TRUSTLINE_{label.upper()}":
                    violations.append(
                        f"{rel}:{lineno}: quickstart prose names an older "
                        f"release label `{match.group(0)}`, but the current "
                        f"release is `TRUSTLINE_{label.upper()}` "
                        f"(docs/RELEASE_MANIFEST.md) — update the prose"
                    )
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in RELEASE_VERSION_PROSE_RE.finditer(line):
                if match.group(1) != version:
                    violations.append(
                        f"{rel}:{lineno}: prose says \"release version "
                        f"{match.group(1)}\", but the current release "
                        f"version is {version} "
                        f"(docs/RELEASE_MANIFEST.md) — update the prose"
                    )


def check_archive_names(root: Path, files: list[Path], violations: list[str]) -> None:
    """Check 5: quickstart hash commands name the current final archive.

    Raises ValueError when the manifest filename cannot be read (a
    source error, exit 2 — never a silent skip: the gate must not
    pass a quickstart it could not compare).
    """
    expected = read_current_archive_filename(root)
    for path in files:
        if path.name not in QUICKSTART_REGIONS:
            continue
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in quickstart_region_lines(
            text, QUICKSTART_REGIONS[path.name]
        ):
            # An explicit variable ($ZIP, ${ARCHIVE}, ...) is the
            # supported parameterized form: no concrete name to check.
            if "$" in line:
                continue
            if "CANDIDATE" in line:
                violations.append(
                    f"{rel}:{lineno}: quickstart names a "
                    f"CANDIDATE archive — current quickstart "
                    f"commands must name the released final archive "
                    f"({expected}) or an explicit variable ($ZIP); "
                    f"historical sections may name old archives, "
                    f"quickstart may not"
                )
                continue
            for name in ZIP_NAME_RE.findall(line):
                if name != expected:
                    violations.append(
                        f"{rel}:{lineno}: quickstart names archive "
                        f"`{name}`, but the current release filename "
                        f"is `{expected}` "
                        f"(docs/RELEASE_MANIFEST.md) — update the "
                        f"command or use an explicit variable ($ZIP)"
                    )

BACKTICK_TOKEN_RE = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")
BACKTICK_FIELD_RE = re.compile(r"`([a-z][a-z0-9_]{2,})`")
UPPER_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

DEFAULT_SCAN = (
    "docs",
    "README.md",
    "SECURITY.md",
    "example-reports",
    "frontend/src",
    "scripts/test-matrix.md",
)

# Files/directories never scanned (build artefacts, caches, data).
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "test-results",
    "data",
    "screenshots",
}
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".db", ".lock")


def find_models_file(root: Path) -> Path:
    """Locate backend/src/identityforge/models.py in either layout."""
    for candidate in (
        root / "backend" / "src" / "identityforge" / "models.py",
        root / "src" / "identityforge" / "models.py",
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "models.py not found under <root>/backend/src or <root>/src; "
        "pass --root pointing at the repository root"
    )


def parse_models(models_path: Path) -> tuple[set[str], set[str]]:
    """Return (FailureReason values, report-model field names)."""
    tree = ast.parse(models_path.read_text(encoding="utf-8"))
    reasons: set[str] = set()
    fields: set[str] = set()
    report_models = {
        "FailureReason",
        "ComparisonResult",
        "TransactionStep",
        "ValidationCheck",
        "ReproducibilityMetadata",
        "EvidenceArtifact",
        "Finding",
        "ScenarioDefinition",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name not in report_models:
            continue
        for item in node.body:
            if isinstance(item, ast.Assign) and node.name == "FailureReason":
                value = item.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    reasons.add(value.value)
            elif isinstance(item, ast.AnnAssign) and isinstance(
                item.target, ast.Name
            ):
                fields.add(item.target.id)
    if not reasons:
        raise ValueError(f"no FailureReason values parsed from {models_path}")
    if not fields:
        raise ValueError(f"no report-model fields parsed from {models_path}")
    return reasons, fields


def harvest_source_tokens(root: Path) -> tuple[set[str], int]:
    """Collect UPPER_SNAKE tokens that exist in the source tree.

    Any backticked token in the docs that appears as a string literal
    or identifier in backend/src, frontend/src, scripts, the Compose
    files, or the CI workflow is a real constant, not drift.

    IF-V5-01 (v6): the SKIP_DIRS filter is applied to path components
    RELATIVE TO THE PROJECT ROOT (resolved paths), never to absolute
    p.parts. A checkout under an ancestor named `data`, `scripts`,
    `node_modules` or `test-results` must not change the result;
    only directories BELOW the root are excluded. A file that
    resolves outside the root (symlink escape) is skipped, never
    followed. Returns (tokens, number of source files harvested);
    the caller fails the gate when the count is zero, so a silent
    empty harvest can never read as a pass.
    """
    tokens: set[str] = set()
    root = root.resolve()
    harvest_roots = [
        root / "backend" / "src",
        root / "frontend" / "src",
        root / "scripts",
        root / "docker-compose.yml",
        root / "docker-compose.test.yml",
        root / ".github" / "workflows" / "ci.yml",
    ]
    seen: set[Path] = set()
    harvested = 0
    for base in harvest_roots:
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = [
                p
                for p in base.rglob("*")
                if p.is_file() and p.suffix not in SKIP_SUFFIXES
            ]
        else:
            continue
        for path in files:
            # Never harvest from this script itself: it has to list the
            # retired codes in DENYLIST, and harvesting them would make
            # them look like legitimate constants.
            if path.name == "validate-docs-contract.py":
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                # Symlink escape: the file lives outside the project
                # root. Skip it — never follow it into the harvest.
                print(
                    f"docs-contract: skipping symlinked source outside "
                    f"root: {path}",
                    file=sys.stderr,
                )
                continue
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            harvested += 1
            try:
                text = resolved.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            tokens.update(UPPER_TOKEN_RE.findall(text))
    return tokens, harvested


def collect_scan_files(root: Path, scan: list[str]) -> list[Path]:
    """Resolve --scan entries to files, skipping artefacts and caches.

    IF-V5-01 (v6): the SKIP_DIRS filter is applied to components
    relative to the root, and a scan entry (or a file under it) that
    resolves outside the root (symlink escape) is refused — a scan
    entry escaping the root raises FileNotFoundError, an individual
    symlinked file is skipped with a warning. A harmless ancestor
    named `data`, `scripts`, `node_modules` or `test-results` never
    changes what is scanned.
    """
    root = root.resolve()
    files: list[Path] = []
    for entry in scan:
        path = (root / entry).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise FileNotFoundError(
                f"scan path escapes the project root: {entry}"
            )
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for found in sorted(path.rglob("*")):
                if not found.is_file():
                    continue
                if found.suffix in SKIP_SUFFIXES:
                    continue
                try:
                    rel = found.resolve().relative_to(root)
                except ValueError:
                    print(
                        f"docs-contract: skipping symlinked scan file "
                        f"outside root: {found}",
                        file=sys.stderr,
                    )
                    continue
                if any(part in SKIP_DIRS for part in rel.parts):
                    continue
                if found.name == "validate-docs-contract.py":
                    continue
                files.append(found)
        else:
            raise FileNotFoundError(f"scan path does not exist: {entry}")
    return files


def check_text_file(
    path: Path,
    rel: str,
    reasons: set[str],
    fields: set[str],
    allowed_tokens: set[str],
    violations: list[str],
) -> None:
    """Denylist + backticked-token + report-field checks for one file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    is_history = rel in HISTORY_FILES
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not is_history:
            for stale in DENYLIST:
                if stale in line:
                    violations.append(
                        f"{rel}:{lineno}: retired code/key `{stale}` "
                        f"(enum/field says otherwise -- see "
                        f"backend/src/identityforge/models.py)"
                    )
        for token in BACKTICK_TOKEN_RE.findall(line):
            if token not in allowed_tokens:
                violations.append(
                    f"{rel}:{lineno}: backticked token `{token}` is not a "
                    f"FailureReason value and appears in no source file; "
                    f"if it is a reason code, use the exact enum value, "
                    f"otherwise add it to CURATED_ALLOWLIST with a source"
                )
        for field in BACKTICK_FIELD_RE.findall(line):
            if field.startswith(REPORT_FIELD_PREFIXES) and field not in fields:
                if field in ("evidence_hash", *FIELD_ALLOWLIST):
                    continue
                violations.append(
                    f"{rel}:{lineno}: backticked report field `{field}` "
                    f"is not a field of the run-report models "
                    f"(ComparisonResult et al. in models.py)"
                )


def _walk_reason_values(obj: object, path: tuple[str, ...]) -> list[str]:
    """Collect reason-code string values at REASON_VALUE_PATHS."""
    values: list[str] = []
    if not path:
        if isinstance(obj, str):
            values.append(obj)
        return values
    head, *rest = path
    if head == "*":
        if isinstance(obj, list):
            for item in obj:
                values.extend(_walk_reason_values(item, tuple(rest)))
    elif isinstance(obj, dict) and head in obj:
        values.extend(_walk_reason_values(obj[head], tuple(rest)))
    return values


def check_json_file(
    path: Path, rel: str, reasons: set[str], fields: set[str], violations: list[str]
) -> None:
    """Key + reason-value checks for single-run report JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        violations.append(f"{rel}: not valid JSON ({exc})")
        return
    if not isinstance(data, dict) or "scenario_id" not in data:
        # Not a single-run report (e.g. a verify-all summary); the
        # denylist still applies to it via the text check, but the
        # key/value contract is for run reports only.
        return
    for key in data:
        if key not in fields and key not in JSON_KEY_ALLOWLIST:
            violations.append(
                f"{rel}: JSON key `{key}` is not a run-report model "
                f"field (ComparisonResult et al. in models.py)"
            )
    for dotted in REASON_VALUE_PATHS:
        for value in _walk_reason_values(data, tuple(dotted.split("."))):
            if value not in reasons:
                violations.append(
                    f"{rel}: reason value `{value}` at `{dotted}` is not "
                    f"a FailureReason value"
                )
    # The same denylist applies to JSON string values.
    text = path.read_text(encoding="utf-8")
    for stale in DENYLIST:
        if stale in text:
            violations.append(
                f"{rel}: retired code/key `{stale}` in example JSON "
                f"(use the exact enum value / model field)"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if docs/example JSON name a reason code or "
        "report field the source does not define (IF-V4-06)."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--scan",
        nargs="*",
        default=list(DEFAULT_SCAN),
        help="paths relative to --root to scan (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    root = Path(args.root).resolve() if args.root else script_dir.parent
    try:
        models_path = find_models_file(root)
        reasons, fields = parse_models(models_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    harvested_tokens, harvested_files = harvest_source_tokens(root)
    allowed_tokens = reasons | harvested_tokens | set(CURATED_ALLOWLIST)
    if harvested_files == 0:
        # IF-V5-01 (v6): a harvest of zero source files means the gate
        # looked at nothing — failing here is the only honest result.
        # (The v5 bug produced exactly this shape silently: every
        # source file skipped, then 104 false violations. An empty
        # harvest must never read as a pass OR as drift — it is a
        # source error, exit 2.)
        print(
            "ERROR: docs-contract harvested 0 source files under "
            f"{root} — refusing to pass a gate on an empty harvest",
            file=sys.stderr,
        )
        return 2
    try:
        files = collect_scan_files(root, list(args.scan))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    violations: list[str] = []
    checked = 0
    for path in files:
        rel = str(path.relative_to(root))
        if path.suffix == ".json":
            check_json_file(path, rel, reasons, fields, violations)
            # JSON files also get the text-level denylist/token checks
            # for any prose they carry (values are covered above too).
            check_text_file(path, rel, reasons, fields, allowed_tokens, violations)
        elif path.suffix in {".md", ".ts", ".tsx", ".py", ".sh", ".ps1", ".yml"}:
            check_text_file(path, rel, reasons, fields, allowed_tokens, violations)
        else:
            continue
        checked += 1

    if checked == 0:
        # IF-V5-01 (v6): a scan of zero files is not a pass.
        print(
            "ERROR: docs-contract scanned 0 files "
            f"(scan entries: {list(args.scan)}) — refusing to pass a "
            "gate on an empty scan",
            file=sys.stderr,
        )
        return 2

    try:
        check_archive_names(root, files, violations)
        check_stale_release_prose(root, files, violations)
        check_active_counts(root, files, violations)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"docs-contract: {len(reasons)} FailureReason values, "
        f"{len(fields)} report-model fields, {harvested_files} source "
        f"files harvested, {checked} files scanned, "
        f"{len(violations)} violation(s)"
    )
    for violation in violations:
        print(f"  FAIL {violation}")
    if violations:
        print(
            "docs-contract: FAILED -- fix the codes/fields above to the "
            "exact enum values / model fields, or (for a genuinely "
            "documented non-reason constant) add it to "
            "CURATED_ALLOWLIST with a source reference."
        )
        return 1
    print("docs-contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
