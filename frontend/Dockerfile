# IdentityForge frontend — infrastructure only (no application source here).
# The frontend agent owns src/**, package.json and vite.config.*.
#
# PRODUCTION BUILD image (P0-04): the container serves the BUILT bundle
# via `vite preview`, not the Vite development server. The dev server
# (HMR, source serving, fs middleware) must not be the shipped entry
# point — several published Vite advisories (CVE-2025-24010,
# CVE-2025-32395, CVE-2025-46565, CVE-2025-62522) concern exactly that
# server. `vite preview` serves only dist/ plus the /api and /auth
# reverse proxy (see vite.config.ts preview section). Localhost-only
# threat model: Compose publishes the port on 127.0.0.1 only, and the
# preview server is not hardened for any other exposure.
#
# IF-V8-42 (v8.0.5) — non-root runtime: the preview server runs as the
# dedicated user `identityforge` (UID/GID 10001, its own group, no
# other groups, no capabilities) — the same app UID as the backend,
# so one attestation covers every app process. 10001 is deliberately
# NOT the image's built-in `node` user (UID 1000): 1000 collides
# with the common host first-user UID. Build steps (apt, npm ci,
# build) still run as root at BUILD time, then /app and the user's
# home are chowned to the app user BEFORE the USER switch, so the
# non-root preview can read dist/ + node_modules and npm has a
# writable HOME for its logs/cache. The Dockerfile contains no
# `USER root` — the image NEVER runs as root, not even at startup.
FROM node:24-slim

# Dedicated non-root app user, created before anything it must own.
RUN groupadd -r identityforge -g 10001 \
    && useradd -r -m -u 10001 -g identityforge identityforge

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# IF-V8-42: hand /app (dist/, node_modules/, caches) and the app
# user's home to the non-root user. npm ci / build ran as root so
# the tree is complete and deterministic; ownership — not a rebuild
# as the user — is what the runtime needs.
RUN mkdir -p /home/identityforge \
    && chown -R identityforge:identityforge /app /home/identityforge

ENV HOME=/home/identityforge

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
    CMD curl -fsS http://127.0.0.1:5173/

# Non-root app user (numeric UID:GID so the identity is exact even
# without a passwd lookup). The vite preview server runs as 10001:10001.
USER 10001:10001

CMD ["npm", "run", "preview:docker"]
