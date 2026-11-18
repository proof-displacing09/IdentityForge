#!/usr/bin/env bash
# IdentityForge stop — clean shutdown, keeps synthetic data for next start.
# To destroy the synthetic Keycloak data as well, use:
#   ./scripts/reset.sh --confirm
set -euo pipefail

cd "$(dirname "$0")/.."

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker / 'docker compose' is not available."
  exit 1
fi

echo "Stopping IdentityForge lab (data preserved)..."
docker compose down
echo "Stopped. Synthetic data is preserved; restart with ./scripts/start.sh."
echo "To wipe synthetic data instead, run: ./scripts/reset.sh --confirm"
