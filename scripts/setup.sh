#!/usr/bin/env bash
# IdentityForge setup — first-time (or repeatable) local installation.
# What it does: checks prerequisites, generates a private .env if missing,
# pulls/builds the Compose images, and boots the lab.
# What it does NOT do: it never touches real identity providers, never
# exposes a port beyond 127.0.0.1, and never deletes data (see reset.sh).
# Internet is needed during setup (image + package downloads). Afterwards
# the lab runs fully locally.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "== IdentityForge setup =="
echo "Project root: $ROOT"
echo

# --- Prerequisites ---------------------------------------------------------
missing=0
# Docker-only boot: Python/Node are NOT required on the host (P1-20).
# They are needed only for the host offline test suites (test-all.sh).
for cmd in docker; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "MISSING: $cmd is not installed. See docs/WINDOWS_SETUP.md or README.md."
    missing=1
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  echo "MISSING: 'docker compose' (Compose v2) is not available."
  missing=1
fi
if [ "$missing" -ne 0 ]; then
  echo "Setup cannot continue. Install the missing tools, then re-run $0."
  exit 1
fi
echo "Prerequisites OK: docker, docker compose."
echo

# --- Local config ----------------------------------------------------------
if [ ! -f .env ]; then
  if [ "$(grep -c '^KEYCLOAK_ADMIN_PASSWORD=' .env.example)" -ne 1 ]; then
    echo "ERROR: expected exactly one admin password setting." >&2
    exit 1
  fi

  admin_password="$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')"

  if [ "${#admin_password}" -ne 64 ]; then
    echo "ERROR: secure password generation failed." >&2
    exit 1
  fi

  umask 077
  sed "s|^KEYCLOAK_ADMIN_PASSWORD=.*$|KEYCLOAK_ADMIN_PASSWORD=${admin_password}|" .env.example > .env

  echo "Created private .env with a unique random admin password."
else
  echo ".env already exists; leaving it untouched."
fi
echo

# --- Build + boot ----------------------------------------------------------
echo "Pulling/building images (first run downloads Keycloak ~1 GB; be patient)..."
docker compose pull keycloak || echo "NOTE: could not pull Keycloak image; continuing with local cache if present."
docker compose up --build -d

echo
echo "Waiting for services to become healthy (this can take 1-2 minutes for Keycloak)..."
./scripts/doctor.sh

echo
echo "== Setup complete =="
echo "Portal / research console:  http://127.0.0.1:5173"
echo "Backend health:             http://127.0.0.1:8000/api/v1/health"
echo "Keycloak admin (lab only):  http://127.0.0.1:8080/admin  (admin / see .env)"
echo "Synthetic users: student_01 (member), officer_01 (member + officer)"
echo "See README.md and docs/REVIEWER_GUIDE.md for the first walkthrough."
