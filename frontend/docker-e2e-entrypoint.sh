#!/bin/sh
# IdentityForge E2E entrypoint (test-only, P0-02).
#
# Problem: Keycloak redirects the browser to http://127.0.0.1:8080
# (KC_HOSTNAME), and the E2E specs default to http://127.0.0.1:5173 —
# but inside this container 127.0.0.1 is the container itself, not
# the lab. Solution: socat loopback forwarders that map the
# container's own loopback ports onto the Compose services, so the
# browser's canonical URLs work unchanged (no config override, no
# PLAYWRIGHT_BASE_URL change, no host-network mode — which Docker
# Desktop on Windows does not support for Linux containers).
#
#   127.0.0.1:5173 -> frontend:5173
#   127.0.0.1:8000 -> backend:8000
#   127.0.0.1:8080 -> keycloak:8080
#
# The forwarders are plain userspace TCP proxies (no privileges,
# no iptables). IF-V8-41 (v8, WS2): each listener binds 127.0.0.1
# explicitly — a bare TCP-LISTEN binds all interfaces inside the
# container, which contradicts "loopback forwarders" and would expose
# the forwarded lab ports to every container on the Compose network.
# before launching Playwright, then execs the given command
# (default: npm run test:e2e).
set -eu

# IF-V8-42 (v8.0.5): the E2E run is non-root (USER 10001:10001), so
# the screenshots/report bind mounts must be writable by that user.
# Docker Desktop normally maps host bind mounts writable, but if a
# host directory arrives root-owned or read-only inside the VM, the
# run would otherwise fail later with a cryptic Playwright error.
# Fail closed HERE, before starting socat, with a precise message:
# ensure each directory (creating it when the mount is absent) and
# prove writability. The mount points do not exist in the image
# (excluded from the build context), so `mkdir -p` also covers the
# no-mount case. Nothing here escalates privileges or changes
# ownership of host paths — if the directory cannot be made
# writable by the app user, the run stops.
for required_dir in /app/e2e/screenshots /app/test-results; do
  if ! mkdir -p "$required_dir" 2>/dev/null; then
    echo "e2e entrypoint: cannot create ${required_dir} (bind mount missing or read-only?)" >&2
    echo "e2e entrypoint: the E2E container runs as non-root UID 10001; make the host directory writable (e.g. pre-create ./test-results/e2e-screenshots and ./test-results before the run) and retry" >&2
    exit 1
  fi
  if [ ! -w "$required_dir" ]; then
    echo "e2e entrypoint: ${required_dir} is not writable by UID 10001 (non-root E2E user)" >&2
    echo "e2e entrypoint: the bind-mounted host directory is owned by another user or mounted read-only; make it writable by UID 10001 and retry" >&2
    exit 1
  fi
done

socat TCP-LISTEN:5173,bind=127.0.0.1,fork,reuseaddr TCP:frontend:5173 &
socat TCP-LISTEN:8000,bind=127.0.0.1,fork,reuseaddr TCP:backend:8000 &
socat TCP-LISTEN:8080,bind=127.0.0.1,fork,reuseaddr TCP:keycloak:8080 &
# The forwarders are children of this process; `exec` below replaces
# the shell with Playwright, and container teardown reaps them.

# Per-port readiness probes (the backend has no `/` route — probe
# /api/v1/health; Keycloak's discovery proves the realm is imported).
for target in "5173:/" "8000:/api/v1/health" "8080:/realms/identityforge-lab/.well-known/openid-configuration"; do
  port="${target%%:*}"
  path="${target#*:}"
  ok=0
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${port}${path}" >/dev/null 2>&1; then ok=1; break; fi
    sleep 2
  done
  if [ "$ok" -ne 1 ]; then
    echo "e2e entrypoint: loopback forwarder on 127.0.0.1:${port}${path} never answered" >&2
    exit 1
  fi
done

echo "e2e entrypoint: loopback forwarders ready (5173/8000/8080)"
exec "$@"
