#!/usr/bin/env bash
# IdentityForge reset — DESTRUCTIVE for synthetic lab data only.
# Removes the Compose containers AND the named Keycloak volume, so the next
# start re-imports the realm and synthetic users from
# keycloak/realm-import/identityforge-lab-realm.json.
# It deletes NO user files, NO real data, and nothing outside this lab:
# the only volume removed is the synthetic Keycloak volume.
# Refuses to run without the explicit flag:  ./scripts/reset.sh --confirm
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${1:-}" != "--confirm" ]; then
  echo "Refusing to reset without confirmation."
  echo "This destroys the SYNTHETIC Keycloak data volume (realm + test users"
  echo "will be re-imported on next start; backend session/evidence state is"
  echo "also recreated). Nothing else is touched."
  echo
  echo "To proceed, run:  $0 --confirm"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker / 'docker compose' is not available."
  exit 1
fi

echo "Resetting IdentityForge lab (synthetic data only)..."
docker compose down -v
echo "Reset complete. Synthetic Keycloak data removed."
echo "Start again with:  ./scripts/start.sh"
