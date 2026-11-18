#!/usr/bin/env python3
"""Docker build-context exclusion tests (IF-V4-02, v5).

Proves the frontend/backend .dockerignore files exclude exactly what
must never enter an image — host node_modules, the shipped E2E
screenshots (100 PNGs in v5), dist, caches, test artefacts, .env files,
the runtime evidence database — while keeping everything the images
need (source, lockfiles, test files, E2E spec files, package metadata).

The matcher below implements Docker's .dockerignore semantics for
the pattern forms used here (Go filepath.Match plus '**', basename
matching for slash-less patterns, last-match-wins with '!' negation,
directory pruning). It is a STATIC verification: the actual
`docker build` context-transfer inspection is NOT RUN in this sandbox
(no Docker). Reviewer commands (Docker machine):
    docker build -f frontend/Dockerfile frontend
    docker build -f frontend/Dockerfile.e2e frontend
  with a fake host frontend/node_modules present, then compare the
  context transfer size and confirm no host node_modules file lands
  in the image:
    docker run --rm <image> ls /app/node_modules | head

Exit 0 when every exclusion/inclusion assertion holds, 1 otherwise.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pattern_to_regex(pattern):
    """Translate one .dockerignore pattern (no leading '!') to a regex
    matching either a full '/'-separated relative path (patterns
    containing '/') or a basename (slash-less patterns, per Docker)."""
    pattern = pattern.rstrip("/")
    segments = pattern.split("/")
    parts = []
    for seg in segments:
        if seg == "**":
            parts.append(".*")
        else:
            buf = []
            i = 0
            while i < len(seg):
                ch = seg[i]
                if ch == "*":
                    buf.append("[^/]*")
                elif ch == "?":
                    buf.append("[^/]")
                elif ch == "[":
                    # Go filepath.Match character class: copy through
                    # to the closing ']' (supports ranges and [^...]).
                    j = seg.find("]", i + 1)
                    if j == -1:
                        buf.append("\\[")
                    else:
                        buf.append(seg[i:j + 1])
                    i = j if j != -1 else i
                elif ch in ".+()|^${}\\":
                    buf.append("\\" + ch)
                else:
                    buf.append(ch)
                i += 1
            parts.append("".join(buf))
    return re.compile("^(?:" + "/".join(parts) + ")$")


class Dockerignore:
    def __init__(self, text):
        self.rules = []  # (negated, regex, basename_only, original)
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            # A trailing '/' marks a directory-only pattern; the
            # matcher treats it as matching the directory path itself
            # (children are pruned by the walker).
            basename_only = "/" not in line.rstrip("/")
            self.rules.append((negated, pattern_to_regex(line), basename_only, raw))

    def _matches(self, rel_posix, is_dir):
        """Last matching rule decides; returns True when excluded."""
        excluded = False
        for negated, regex, basename_only, _raw in self.rules:
            candidate = rel_posix.rsplit("/", 1)[-1] if basename_only else rel_posix
            if regex.match(candidate):
                excluded = not negated
        return excluded

    def is_excluded(self, rel_posix, is_dir=False):
        return self._matches(rel_posix, is_dir)

    def walk_included(self, base):
        """Yield relative POSIX paths (files only) that survive the
        ignore rules, pruning excluded directories like Docker."""
        base = Path(base)
        included = []
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = Path(dirpath).relative_to(base)
            # Prune excluded directories first (deepest-first safe:
            # os.walk yields top-down, so modifying dirnames works).
            keep_dirs = []
            for d in dirnames:
                rel = (rel_dir / d).as_posix() if str(rel_dir) != "." else d
                if not self.is_excluded(rel, is_dir=True):
                    keep_dirs.append(d)
            dirnames[:] = keep_dirs
            for f in filenames:
                rel = (rel_dir / f).as_posix() if str(rel_dir) != "." else f
                if not self.is_excluded(rel):
                    included.append(rel)
        return included


PASS = 0
FAIL = 0


def check(desc, actual, expected):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"PASS: {desc}")
    else:
        FAIL += 1
        print(f"FAIL: {desc} — expected {expected!r}, got {actual!r}")


def build_fake_tree(root, files):
    for rel in files:
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fake content\n")


FRONTEND_FAKE = [
    # Must be EXCLUDED
    "node_modules/fake-native/index.js",
    "node_modules/fake-native/bin/fake-native",
    "node_modules/.bin/fake-native",
    "node_modules/some-pkg/package.json",
    "dist/assets/index-abc123.js",
    "dist/index.html",
    ".vite/deps/_metadata.json",
    "e2e/screenshots/1280x800-overview.png",
    "e2e/screenshots/390x844-portal-signed-in.png",
    "e2e/.cache/ms-playwright/chromium-1234/chrome-linux/chrome",
    "test-results/playwright-report.json",
    "test-results/e2e-screenshots/shot.png",
    "playwright-report/index.html",
    "coverage/lcov.info",
    ".env",
    ".env.local",
    ".git/config",
    "debug.log",
    "archive.zip",
    ".DS_Store",
    # Must be INCLUDED
    "package.json",
    "package-lock.json",
    ".env.example",
    "Dockerfile",
    "Dockerfile.e2e",
    "docker-e2e-entrypoint.sh",
    "index.html",
    "playwright.config.ts",
    "vite.config.ts",
    "tsconfig.json",
    "README.md",
    "src/App.tsx",
    "src/main.tsx",
    "src/pages/Overview.tsx",
    "e2e/portal.spec.ts",
    "e2e/edge.spec.ts",
    "e2e/a11y.spec.ts",
    "e2e/screenshots.spec.ts",
]

BACKEND_FAKE = [
    # Must be EXCLUDED
    ".venv/bin/python",
    ".venv/lib/python3.12/site-packages/fake/__init__.py",
    "venv/Scripts/python.exe",
    "data/identityforge.db",
    "data/other.sqlite3",
    "stray.db",
    "src/identityforge/__pycache__/app.cpython-312.pyc",
    "src/identityforge/api/app.pyc",
    ".pytest_cache/v/cache/lastfailed",
    ".ruff_cache/abc",
    ".mypy_cache/x/data.json",
    ".coverage",
    "htmlcov/index.html",
    "test-results/audit-backend.log",
    "dist/pkg-1.0-py3-none-any.whl",
    "build/lib/fake.py",
    "identityforge.egg-info/PKG-INFO",
    ".env",
    ".env.local",
    ".git/config",
    "app.log",
    "archive.tar.gz",
    ".DS_Store",
    # Must be INCLUDED
    "src/identityforge/api/app.py",
    "src/identityforge/models.py",
    "tests/unit/test_transport.py",
    "tests/test_cli.py",
    "pyproject.toml",
    "requirements-freeze.txt",
    "requirements.txt",
    "pytest.ini",
    "Dockerfile",
    "README.md",
    ".env.example",
]


def main():
    frontend_ignore = (ROOT / "frontend" / ".dockerignore").read_text()
    backend_ignore = (ROOT / "backend" / ".dockerignore").read_text()
    check("frontend/.dockerignore exists and is non-empty", bool(frontend_ignore.strip()), True)
    check("backend/.dockerignore exists and is non-empty", bool(backend_ignore.strip()), True)

    with tempfile.TemporaryDirectory() as tmp:
        fe = Path(tmp) / "frontend"
        build_fake_tree(fe, FRONTEND_FAKE)
        di = Dockerignore(frontend_ignore)
        included = set(di.walk_included(fe))
        excluded = {f for f in FRONTEND_FAKE if f not in included}
        for f in FRONTEND_FAKE:
            if f.startswith(("node_modules/", "dist/", ".vite/", "e2e/screenshots/",
                             "e2e/.cache/", "test-results/", "playwright-report/",
                             "coverage/", ".git/")) or f in (
                    ".env", ".env.local", "debug.log", "archive.zip", ".DS_Store"):
                check(f"frontend excludes {f}", f in excluded, True)
            else:
                check(f"frontend keeps {f}", f in included, True)
        # The fake host node_modules tree (the IF-V4-02 breakage) is
        # excluded as a whole: no host module can overwrite the
        # container's `npm ci` install.
        check("frontend excludes the whole fake host node_modules tree",
              all(f in excluded for f in FRONTEND_FAKE if f.startswith("node_modules/")), True)

        be = Path(tmp) / "backend"
        build_fake_tree(be, BACKEND_FAKE)
        di = Dockerignore(backend_ignore)
        included = set(di.walk_included(be))
        excluded = {f for f in BACKEND_FAKE if f not in included}
        for f in BACKEND_FAKE:
            if f.startswith((".venv/", "venv/", "data/", "__pycache__/",
                             ".pytest_cache/", ".ruff_cache/", ".mypy_cache/",
                             "htmlcov/", "test-results/", "dist/", "build/",
                             ".git/")) or f.endswith((".db", ".sqlite3", ".pyc", ".log",
                                                     ".tar.gz")) or f in (
                    ".coverage", ".env", ".env.local", ".DS_Store") or ".egg-info/" in f:
                check(f"backend excludes {f}", f in excluded, True)
            else:
                check(f"backend keeps {f}", f in included, True)
        check("backend excludes the runtime evidence database",
              "data/identityforge.db" in excluded, True)

    # --- Real tree: what would actually enter the build contexts ------
    fe_real = Dockerignore(frontend_ignore)
    fe_included = fe_real.walk_included(ROOT / "frontend")
    fe_all = [p.relative_to(ROOT / "frontend").as_posix()
              for p in (ROOT / "frontend").rglob("*") if p.is_file()]
    fe_excluded = [p for p in fe_all if p not in set(fe_included)]
    check("real frontend: node_modules fully excluded",
          all(p.startswith("node_modules/") for p in fe_excluded if p.startswith("node_modules/"))
          and not any(p.startswith("node_modules/") for p in fe_included), True)
    # (v5, WS3 added a 100th PNG — count from the tree, never hardcode.)
    shots_total = sum(1 for p in fe_all if p.startswith("e2e/screenshots/"))
    check(f"real frontend: e2e/screenshots fully excluded ({shots_total} PNGs)",
          not any(p.startswith("e2e/screenshots/") for p in fe_included)
          and sum(1 for p in fe_excluded if p.startswith("e2e/screenshots/")) == shots_total
          and shots_total >= 99, True)
    check("real frontend: E2E spec files kept",
          all(f"e2e/{s}" in fe_included for s in
              ("portal.spec.ts", "edge.spec.ts", "a11y.spec.ts", "screenshots.spec.ts")), True)
    check("real frontend: src + lockfile kept",
          any(p.startswith("src/") for p in fe_included)
          and "package-lock.json" in fe_included and "package.json" in fe_included, True)
    fe_inc_bytes = sum((ROOT / "frontend" / p).stat().st_size for p in fe_included)
    fe_exc_bytes = sum((ROOT / "frontend" / p).stat().st_size for p in fe_excluded)
    print(f"INFO: real frontend context: {len(fe_included)} files kept "
          f"({fe_inc_bytes / 1048576:.1f} MiB), {len(fe_excluded)} files excluded "
          f"({fe_exc_bytes / 1048576:.1f} MiB) — static estimate; actual "
          f"`docker build` transfer inspection NOT RUN (no Docker)")

    be_real = Dockerignore(backend_ignore)
    be_included = be_real.walk_included(ROOT / "backend")
    check("real backend: evidence DB excluded",
          not any(p == "data/identityforge.db" for p in be_included), True)
    check("real backend: src + tests + freeze kept",
          any(p.startswith("src/") for p in be_included)
          and any(p.startswith("tests/") for p in be_included)
          and "requirements-freeze.txt" in be_included, True)

    print()
    print(f"dockerignore: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
