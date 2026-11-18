# IdentityForge — backend

SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION.

FastAPI backend for the IdentityForge OAuth/OIDC lab: a real BFF login
flow against a local Keycloak (Compose, reviewer machines), plus a
deterministic offline scenario engine (I1–I18) that compares the secure
validators against isolated flawed fixtures.

## Run

```bash
cd backend
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
../.venv/bin/python -m identityforge.cli doctor
../.venv/bin/python -m identityforge.cli verify-all
../.venv/bin/uvicorn identityforge.api.app:app --host 127.0.0.1 --port 8000
```

## Test

```bash
../.venv/bin/python -m pytest
../.venv/bin/ruff check src tests
```

## Key facts

- Keycloak is **NOT RUN** in this sandbox (no Docker); `/auth/login`
  returns 503 `provider_unavailable` when the IdP is unreachable, never
  a fake login.
- Scenario runs (`POST /api/v1/runs`) are offline fixtures with fresh
  RSA keys per run. Mode is always reported as
  `DETERMINISTIC OFFLINE FIXTURE`.
- Flawed validators live in `src/identityforge/scenarios/flawed.py`,
  are pure functions, and are never exposed via HTTP or used by the portal.
- Sessions are opaque random ids in HttpOnly SameSite=Lax cookies,
  rotated on login, revoked on logout. Roles come from a trusted
  server-side policy map by subject, never from token role claims alone.
- Local HTTP is a localhost development exception only; production
  requires HTTPS and Secure cookies.
```

