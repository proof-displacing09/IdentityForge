# IdentityForge backend — infrastructure only (no application source here).
# The backend agent owns src/identityforge/** and backend/pyproject.toml.
# This Dockerfile installs the pinned dependencies from
# backend/requirements-freeze.txt and runs uvicorn on 0.0.0.0:8000 INSIDE the container (P0-02): a process
# bound to the container loopback cannot be reached through a published
# port. Host exposure stays loopback-only because Compose publishes
# the port on 127.0.0.1 only.
#
# IF-V8-42 (v8.0.5) — non-root runtime: the app process runs as the
# dedicated user `identityforge` (UID/GID 10001, its own group, no
# other groups, no capabilities). 10001 is deliberately NOT 1000:
# the common host first-user UID 1000 collides with the `node` user
# in the frontend image and with host users on bind mounts; 10001
# keeps the lab's app identity distinct everywhere. The Dockerfile
# contains no `USER root` — the image NEVER runs as root, not even
# at startup: the entrypoint is the app server itself, and the
# one-shot `backend-data-prep` Compose service (docker-compose.yml)
# performs the only root action in the lab, preparing /app/data
# before this service starts. See backend/docker/prepare-data-volume.py.
FROM python:3.12-slim

# Dedicated non-root app user, created before anything it must own.
# -r: system user; -m: a real home directory (pip/uvicorn caches and
# HOME-dependent tooling need a writable HOME, not /nonexistent).
RUN groupadd -r identityforge -g 10001 \
    && useradd -r -m -u 10001 -g identityforge identityforge

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-freeze.txt ./requirements-freeze.txt
RUN pip install --no-cache-dir -r requirements-freeze.txt

# Auditor pin (IF-V4-09, v5; IF-V8-42, v8.0.5): the pip-audit version
# used by the dependency gate, pinned separately from the runtime
# freeze so an auditor change is visible and reproducible. Installed
# here AT BUILD TIME into the system site-packages (readable and
# executable by the non-root app user), because the audit gate runs
# as that user and can no longer `pip install` into system
# site-packages at gate time — see scripts/test-all.ps1
# PYTHON_DEPENDENCY_AUDIT. The gate now only runs the tool and
# classifies its exit code; a missing tool is TOOL_UNAVAILABLE
# (NOT RUN, fail-closed under -Strict), never a silent skip.
COPY requirements-audit.txt ./requirements-audit.txt
RUN pip install --no-cache-dir -r requirements-audit.txt

COPY pyproject.toml ./pyproject.toml
COPY src ./src

# IF-V8-42: the one-shot volume-prep script ships in the app image
# so the `backend-data-prep` service (which reuses this image with
# `user: "0:0"`) can run it without a second image. It is stdlib-only
# and never starts the app server.
COPY docker/prepare-data-volume.py ./prepare-data-volume.py

# The evidence directory exists in the image so a plain `docker run`
# (no named volume) still has a writable data path; a named-volume
# mount replaces this directory at runtime, which is why the prep
# service re-asserts ownership on the mounted volume (an image
# chown cannot survive a volume mount).
RUN mkdir -p /app/data /home/identityforge \
    && chown -R identityforge:identityforge /app /home/identityforge

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    HOME=/home/identityforge

EXPOSE 8000

# Healthcheck target: GET /api/v1/health (see docs/API_CONTRACT.md).
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health

# Non-root app user (numeric UID:GID so the identity is exact even
# without a passwd lookup). Everything above ran as root at BUILD
# time; everything from here on — including the uvicorn server —
# runs as 10001:10001.
USER 10001:10001

CMD ["uvicorn", "identityforge.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
