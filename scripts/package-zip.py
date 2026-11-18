#!/usr/bin/env python3
"""Package the IdentityForge v2 tree into the distributable ZIP.

Exclusions (per the v2 directive / verify-release.sh):
  dirs: .venv, node_modules, frontend/dist, .git, test-results (any
  level), backend/data, __pycache__, .pytest_cache, .ruff_cache
  files: *.egg-info (dirs), *.db, *.sqlite, *.zip, *.pem, *.key,
  *.p12, *.jks, *.log, *.bak, *.swp, .env, *Zone.Identifier, .DS_Store
Preserves Unix file modes (so .sh stays executable). Sorted order.
Usage: python3 scripts/package-zip.py <tree> <output.zip>
"""
import os
import sys
import zipfile

EXCLUDE_DIRS = {
    ".venv", "node_modules", "dist", ".git", "test-results",
    "data", "__pycache__", ".pytest_cache", ".ruff_cache", ".cache",
}
# "data" is excluded only under backend/ — handled by path check below.
EXCLUDE_SUFFIXES = (
    ".db", ".sqlite", ".zip", ".pem", ".key", ".p12", ".jks",
    ".log", ".bak", ".swp", "-backup",
)
EXCLUDE_NAMES = {".env", ".DS_Store"}


def excluded(rel: str) -> bool:
    parts = rel.split(os.sep)
    for p in parts:
        if p in ("__pycache__", ".pytest_cache", ".ruff_cache", ".cache",
                 ".venv", "node_modules", ".git", "test-results"):
            return True
        if p.endswith(".egg-info"):
            return True
    if len(parts) > 1 and parts[0] == "frontend" and parts[1] == "dist":
        return True
    if len(parts) > 1 and parts[0] == "backend" and parts[1] == "data":
        return True
    name = parts[-1]
    if name in EXCLUDE_NAMES:
        return True
    if "Zone.Identifier" in name:
        return True
    if any(name.endswith(s) for s in EXCLUDE_SUFFIXES):
        return True
    return False


def main() -> int:
    tree, out = sys.argv[1], sys.argv[2]
    files = []
    for root, dirs, names in os.walk(tree):
        dirs[:] = sorted(d for d in dirs
                         if not excluded(os.path.relpath(os.path.join(root, d), tree)))
        for n in sorted(names):
            full = os.path.join(root, n)
            rel = os.path.relpath(full, tree)
            if not excluded(rel):
                files.append((rel, full))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, full in files:
            st = os.stat(full)
            zi = zipfile.ZipInfo.from_file(full, rel)
            zi.external_attr = (st.st_mode & 0xFFFF) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as f:
                z.writestr(zi, f.read())
    print(f"wrote {out}: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
