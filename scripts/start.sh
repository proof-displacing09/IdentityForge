#!/usr/bin/env bash
# IdentityForge start — boot (or re-boot) the lab.
# Safe to run repeatedly. Does not delete any data.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker / 'docker compose' is not available. See docs/WINDOWS_SETUP.md."
  exit 1
fi

if [ ! -f .env ]; then
  echo "No private .env found; running secure first-time setup."
  exec bash ./scripts/setup.sh
fi

echo "Starting IdentityForge lab (loopback only)..."
docker compose up --build -d
echo
./scripts/doctor.sh
echo
echo "Portal / research console:  http://127.0.0.1:5173"
echo "Backend health:             http://127.0.0.1:8000/api/v1/health"
