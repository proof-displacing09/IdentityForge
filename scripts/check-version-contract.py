#!/usr/bin/env python3
"""Version-contract check (Trustline v8.0.5, IF-V5-05).

One release version, stated once per authoritative source, must agree
everywhere. The v5 tree shipped the release as 1.5.0 in
docs/RELEASE_MANIFEST.md while the backend and frontend sources still
said 1.0.0 (backend/pyproject.toml, __init__.__version__,
FastAPI(version=...), /api/v1/health "version", frontend/package.json
+ package-lock.json) — so no single value could be quoted as "the
version", and a hard-coded 1.5.0 in a doc would have been presented as
proof of deployed source while the running artifact reported 1.0.0.

This script reads every authoritative version value from the tree
(never from memory) and fails unless ALL of them equal the expected
release version (default 1.8.5 for Trustline v8.0.5):

  * docs/RELEASE_MANIFEST.md — the "**Version:**" line of the
    "Operation Trustline v8.0.5" section (the release record).
  * backend/pyproject.toml — [project] version.
  * backend/src/identityforge/__init__.py — __version__
    (WS1 owns the backend single version source; this script only
    READS it — if it disagrees, WS1 bumps the backend, not this file).
  * backend/src/identityforge/api/app.py — FastAPI(version=...) and
    the /api/v1/health "version" (the version the RUNNING backend
    reports; the only version that proves deployed source). WS1's v6
    design makes both DERIVE from __init__.__version__ (a single
    backend version source): the checker accepts either a literal
    "X.Y.Z" or the bare identifier __version__ (resolved through
    __init__.py) and reports which form it found — a literal that
    disagrees still fails, and a derivation from a wrong __version__
    fails through the __init__ source.
  * frontend/package.json + frontend/package-lock.json — root version
    (both: `npm ci` fails if they disagree, so a bump must touch
    both together, via npm, never by hand-editing the lockfile).
  * frontend/src — must contain NO hard-coded version literal: the
    UI shows the version from GET /api/v1/health (Health.version in
    frontend/src/types.ts, getHealth() in frontend/src/api.ts), so a
    literal in UI source would be a second source of truth. Test
    files (*.test.ts[x]) are excluded — a test may assert the API
    version — but shipped UI source may not state one.

Exit 0 = all sources agree with the expected version; 1 = a source
disagrees (the per-source table names it); 2 = a source is missing
or unparseable. Stdlib only; no network, no Docker, no venv needed.

Usage:
  python3 scripts/check-version-contract.py [--root DIR]
      [--expected 1.8.5]
Regression: scripts/test-version-contract.sh (all-agree PASS;
__version__-derivation PASS + negative; one source differing FAILS,
for every source; missing source FAILS).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
QUOTED_VERSION_RE = re.compile(r"""["'](\d+\.\d+\.\d+)["']""")

# Sources that must exist. Each entry: (label, relative path).
REQUIRED_FILES = (
    ("docs/RELEASE_MANIFEST.md", "release manifest"),
    ("backend/pyproject.toml", "backend pyproject"),
    ("frontend/package.json", "frontend package.json"),
    ("frontend/package-lock.json", "frontend package-lock.json"),
    ("backend/src/identityforge/__init__.py", "backend __init__"),
    ("backend/src/identityforge/api/app.py", "backend app.py"),
)


def read_manifest_version(root: Path) -> str:
    """The **Version:** line of the Operation Trustline v8.0.5 section."""
    text = (root / "docs" / "RELEASE_MANIFEST.md").read_text(encoding="utf-8")
    match = re.search(
        r"^## Operation Trustline v8\.0\.5\b.*?"
        r"^\s*-\s*\*\*Version:\*\*\s*(\d+\.\d+\.\d+)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(
            "no '## Operation Trustline v8.0.5' section with a "
            "'**Version:** X.Y.Z' line in docs/RELEASE_MANIFEST.md"
        )
    return match.group(1)


def read_pyproject_version(root: Path) -> str:
    with open(root / "backend" / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    try:
        return str(data["project"]["version"])
    except KeyError as exc:
        raise ValueError(
            "backend/pyproject.toml has no [project] version"
        ) from exc


def read_package_json_version(root: Path) -> str:
    data = json.loads((root / "frontend" / "package.json").read_text())
    if "version" not in data:
        raise ValueError("frontend/package.json has no 'version'")
    return str(data["version"])


def read_package_lock_version(root: Path) -> str:
    data = json.loads((root / "frontend" / "package-lock.json").read_text())
    versions = {str(data.get("version", "")), str(data.get("packages", {}).get("", {}).get("version", ""))}
    versions.discard("")
    if not versions:
        raise ValueError(
            "frontend/package-lock.json has no root package version"
        )
    if len(versions) > 1:
        raise ValueError(
            "frontend/package-lock.json disagrees with itself: "
            f"top-level vs packages[''].version: {sorted(versions)}"
        )
    return versions.pop()


def read_init_version(root: Path) -> str:
    text = (root / "backend" / "src" / "identityforge" / "__init__.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError(
            "backend/src/identityforge/__init__.py has no __version__"
        )
    return match.group(1)


def read_app_versions(root: Path) -> tuple[tuple[str, str], tuple[str, str]]:
    """(FastAPI version, /api/v1/health version) from app.py.

    Each is returned as (resolved_value, derivation): the version
    expression is either a quoted literal ("X.Y.Z") or the bare
    identifier __version__ (WS1's v6 single-source design, carried into v7 — both the
    FastAPI version and the health version derive from
    backend/src/identityforge/__init__.py). A __version__ derivation
    resolves through read_init_version(); a literal is used as-is.
    """
    text = (root / "backend" / "src" / "identityforge" / "api" / "app.py").read_text(
        encoding="utf-8"
    )
    init_v = read_init_version(root)

    def resolve(expr: str, where: str) -> tuple[str, str]:
        if expr == "__version__":
            return init_v, f"via __init__.__version__ ({init_v})"
        if VERSION_RE.match(expr):
            return expr, "literal in app.py"
        raise ValueError(
            f"backend app.py {where} version is neither a quoted "
            f'"X.Y.Z" literal nor __version__: {expr!r}'
        )

    fastapi = re.search(
        r'FastAPI\(\s*title="IdentityForge",\s*version=("[^"]+"|__version__)',
        text,
    )
    if not fastapi:
        raise ValueError(
            'backend app.py has no FastAPI(title="IdentityForge", '
            'version=...) — expected a "X.Y.Z" literal or __version__'
        )
    health = re.findall(r'"version":\s*("[^"]+"|__version__)', text)
    if len(health) != 1:
        raise ValueError(
            "backend app.py must carry exactly one health "
            f'"version" expression, found {len(health)}'
        )
    fastapi_v = resolve(fastapi.group(1).strip('"'), "FastAPI")
    health_v = resolve(health[0].strip('"'), "health")
    return fastapi_v, health_v


def check_ui_version_source(root: Path) -> list[str]:
    """The UI must read its version from the API, never hard-code one.

    Returns a list of problems (empty = clean). Asserts the wiring
    exists (getHealth + Health.version) and that no shipped UI source
    file (excluding tests) carries a quoted version literal.
    """
    problems: list[str] = []
    api_ts = root / "frontend" / "src" / "api.ts"
    types_ts = root / "frontend" / "src" / "types.ts"
    if not api_ts.is_file() or "getHealth" not in api_ts.read_text(
        encoding="utf-8", errors="ignore"
    ):
        problems.append(
            "frontend/src/api.ts has no getHealth() — the UI has no "
            "API version source to read"
        )
    if not types_ts.is_file() or "version?:" not in types_ts.read_text(
        encoding="utf-8", errors="ignore"
    ):
        problems.append(
            "frontend/src/types.ts Health has no version field — the "
            "UI has no API version field to display"
        )
    src = root / "frontend" / "src"
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        if ".test." in path.name:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(),
            start=1,
        ):
            for literal in QUOTED_VERSION_RE.findall(line):
                problems.append(
                    f"hard-coded version literal `{literal}` in "
                    f"{path.relative_to(root)}:{lineno} — the UI must "
                    "read the version from GET /api/v1/health, not "
                    "state one in source"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail unless every authoritative version value "
        "equals the expected release version (IF-V5-05)."
    )
    parser.add_argument(
        "--root", default=None,
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--expected", default="1.8.5",
        help="expected release version (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    if not VERSION_RE.match(args.expected):
        print(f"ERROR: --expected must be X.Y.Z, got {args.expected!r}",
              file=sys.stderr)
        return 2

    script_dir = Path(__file__).resolve().parent
    root = Path(args.root).resolve() if args.root else script_dir.parent

    missing = [rel for rel, _ in REQUIRED_FILES if not (root / rel).is_file()]
    if missing:
        print(
            "ERROR: version-contract sources missing: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    values: list[tuple[str, str, str]] = []
    errors: list[str] = []
    readers = (
        ("docs/RELEASE_MANIFEST.md (Trustline v8.0.5 section)", read_manifest_version),
        ("backend/pyproject.toml [project] version", read_pyproject_version),
        ("frontend/package.json version", read_package_json_version),
        ("frontend/package-lock.json root version", read_package_lock_version),
        ("backend/src/identityforge/__init__.py __version__", read_init_version),
    )
    for label, reader in readers:
        try:
            values.append((label, reader(root), ""))
        except (ValueError, KeyError, OSError, json.JSONDecodeError,
                tomllib.TOMLDecodeError) as exc:
            errors.append(f"{label}: unreadable ({exc})")
    try:
        (fastapi_v, fastapi_note), (health_v, health_note) = read_app_versions(root)
        values.append(("backend app.py FastAPI version", fastapi_v, fastapi_note))
        values.append(("backend app.py /api/v1/health version", health_v, health_note))
    except (ValueError, OSError) as exc:
        errors.append(f"backend app.py versions: unreadable ({exc})")
    ui_problems = check_ui_version_source(root)

    print(f"version-contract: expected {args.expected}")
    mismatches = 0
    for label, value, note in values:
        shown = f"{value} ({note})" if note else value
        if value == args.expected:
            print(f"  OK       {label}: {shown}")
        else:
            print(
                f"  MISMATCH {label}: {shown} "
                f"(expected {args.expected})"
            )
            mismatches += 1
    for problem in ui_problems:
        print(f"  MISMATCH UI version source: {problem}")
        mismatches += 1
    for error in errors:
        print(f"  ERROR    {error}")
    if errors:
        print(
            "version-contract: FAILED — a version source is missing "
            "or unreadable; fix the source, never the check."
        )
        return 2
    if mismatches:
        print(
            "version-contract: FAILED — every authoritative version "
            f"must equal {args.expected}. Bump the owning source "
            "(backend: WS1; frontend package files: via npm so the "
            "lockfile stays in sync; manifest: docs) — do not "
            "hard-code the version into a doc as proof of the "
            "deployed artifact."
        )
        return 1
    print(
        "version-contract: PASS — all authoritative versions equal "
        f"{args.expected} (manifest, pyproject, __init__, FastAPI + "
        "health, package.json + lockfile; UI reads the version from "
        "GET /api/v1/health)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
