#!/usr/bin/env python3
"""Compose-file validation fallback (no Docker CLI available).

Requires PyYAML (third-party, NOT stdlib): the checks below parse
real YAML. If PyYAML is missing for the interpreter running this
file, it exits 2 with ENVIRONMENT NOT READY (see the import guard)
instead of a traceback — a missing test prerequisite is never a
Compose defect. The regression harness
(scripts/test-compose-healthcheck-regressions.sh) preflights PyYAML
in the same interpreter before invoking this checker (IF-V7.2-02).

Checks docker-compose.yml (and docker-compose.test.yml) parse as YAML
and that the invariants the lab depends on hold: the three services
exist, published ports are the locked loopback ports 8080/8000/5173,
no ${..._PORT} interpolation remains, and Keycloak is pinned to 26.8.2.

IF-V4-01 (v5, P0) — Docker Compose healthcheck interpolation:
  Docker Compose interpolates $VAR and ${VAR} in configuration
  values BEFORE the container shell runs, so a single-dollar shell
  variable such as '$resp' in a healthcheck is replaced by an empty
  string and the probe inspects blank text. This check therefore
    (a) rejects any single-$ shell-variable reference in every
        healthcheck / command / entrypoint scalar of every Compose
        file, while allowing the legitimate escapes '$$' (literal
        dollar) and '${ENV:-default}' interpolation, and
    (b) simulates Compose interpolation on the Keycloak healthcheck
        and asserts the RESOLVED command still contains the literal
        shell assignment 'resp=$(cat <&3)' and both 'echo "$resp"'
        references, plus the two strict greps (HTTP 200 status line
        and the "issuer" field).
  It also verifies backend/frontend declare depends_on
  service_healthy on keycloak/backend respectively — the healthcheck
  is what gates the stack, so a silently dropped depends_on would
  let the backend start against an unready Keycloak.

This is NOT `docker compose config -q`: it cannot resolve env
interpolation against the real environment, service references, or
healthcheck syntax. When Docker is present, test-all.sh runs the
real command instead, and scripts/test-compose-healthcheck.sh
additionally checks the RESOLVED healthcheck via
`docker compose config` plus the live health state. Exit 0 on
pass, 1 on any violation.
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML is a real prerequisite, not stdlib.
    # IF-V7.2-02 (v7.3): fail with a labelled ENVIRONMENT NOT READY
    # (exit 2), never a bare ModuleNotFoundError traceback that a
    # caller could misread as a Compose or healthcheck defect. The
    # regression harness preflights this in the same interpreter
    # before running; this guard is the backstop for direct runs.
    print("ENVIRONMENT NOT READY: PyYAML is required to validate "
          "docker-compose.yml (scripts/compose-config-check.py imports "
          "yaml), but it is not installed for this interpreter "
          f"({sys.executable}). Install it with "
          "'python3 -m pip install pyyaml' (or your system package "
          "'python3-yaml'), then re-run. This is a missing test "
          "prerequisite, not a Compose or healthcheck defect.")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
COMPOSE_TEST = ROOT / "docker-compose.test.yml"
LOCKED = {"keycloak": "127.0.0.1:8080:8080",
          "backend": "127.0.0.1:8000:8000",
          "frontend": "127.0.0.1:5173:5173"}
CANONICAL_ISSUER = "http://127.0.0.1:8080/realms/identityforge-lab"
errors = []

# --- (a) single-$ shell-variable scan -------------------------------------
# A bare '$' followed by a valid variable-name character is a Compose
# interpolation site: '$resp' would be replaced by the (absent) host
# variable 'resp' — an empty string. Allowed: '$$' (Compose escape
# for a literal dollar) and '${...}' (explicit env interpolation,
# e.g. ${KEYCLOAK_ADMIN_USERNAME:-admin}). '$(' is NOT a variable
# reference — '(' cannot begin a Compose variable name — so command
# substitution such as '$(cat <&3)' passes through unchanged.
SINGLE_DOLLAR = re.compile(r"(?<!\$)\$(?!\$)(?!\{)(?!\()[A-Za-z_]")


def iter_command_scalars(node, path):
    """Yield (path, string) for every healthcheck/command/entrypoint scalar."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("healthcheck", "command", "entrypoint"):
                yield from iter_command_scalars(value, f"{path}.{key}")
            elif key in ("environment", "volumes", "ports", "networks",
                         "depends_on", "profiles", "image", "build"):
                continue
            else:
                yield from iter_command_scalars(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from iter_command_scalars(value, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def check_single_dollar(doc, filename):
    for path, text in iter_command_scalars(doc, filename):
        for m in SINGLE_DOLLAR.finditer(text):
            errors.append(
                f"{filename} {path}: single-$ shell-variable reference "
                f"'{text[max(0, m.start() - 12):m.start() + 16]}' — "
                f"Compose interpolates $VAR before the container shell "
                f"runs; escape in-container variables as '$$VAR' "
                f"(IF-V4-01)")


def simulate_compose_interpolation(text, env=None):
    """Approximate Docker Compose interpolation (documented semantics).

    '$$' -> literal '$'; '${VAR:-default}' -> default (or env value);
    '${VAR}' / '$VAR' -> env value or '' when unset. Anything else is
    left unchanged. This is a static approximation — the authoritative
    check is `docker compose config` (scripts/test-compose-healthcheck.sh).
    """
    env = env or {}
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "$" and i + 1 < len(text) and text[i + 1] == "$":
            out.append("$")
            i += 2
        elif ch == "$" and i + 1 < len(text) and text[i + 1] == "{":
            end = text.find("}", i + 2)
            if end == -1:
                out.append(ch)
                i += 1
            else:
                inner = text[i + 2:end]
                if ":-" in inner:
                    var, default = inner.split(":-", 1)
                    out.append(env.get(var, default))
                else:
                    out.append(env.get(inner, ""))
                i = end + 1
        elif ch == "$" and i + 1 < len(text) and (
                text[i + 1].isalpha() or text[i + 1] == "_"):
            j = i + 1
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            out.append(env.get(text[i + 1:j], ""))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def healthcheck_test_string(service):
    hc = (service or {}).get("healthcheck") or {}
    test = hc.get("test")
    if isinstance(test, list):
        return " ".join(str(t) for t in test)
    return str(test or "")


try:
    doc = yaml.safe_load(COMPOSE.read_text())
except Exception as exc:  # noqa: BLE001 - report any parse failure
    print(f"FAIL: docker-compose.yml does not parse: {exc}")
    sys.exit(1)

services = doc.get("services") or {}
for name, want in LOCKED.items():
    svc = services.get(name)
    if not svc:
        errors.append(f"service {name!r} missing")
        continue
    ports = [str(p) for p in svc.get("ports", [])]
    if want not in ports:
        errors.append(f"service {name!r} ports {ports} do not include locked {want}")

text = COMPOSE.read_text()
if re.search(r"\$\{(KEYCLOAK|BACKEND|FRONTEND)_PORT\}", text):
    errors.append("compose file still interpolates a ${..._PORT} variable "
                  "(ports are locked; see docs)")

kc_image = str((services.get("keycloak") or {}).get("image", ""))
if "26.8.2" not in kc_image:
    errors.append(f"keycloak image {kc_image!r} is not pinned to 26.8.2")

# --- IF-V4-01 (a): single-$ scan over both Compose files -------------------
check_single_dollar(doc, "docker-compose.yml")
if COMPOSE_TEST.exists():
    try:
        test_doc = yaml.safe_load(COMPOSE_TEST.read_text())
    except Exception as exc:  # noqa: BLE001 - report any parse failure
        print(f"FAIL: docker-compose.test.yml does not parse: {exc}")
        sys.exit(1)
    check_single_dollar(test_doc, "docker-compose.test.yml")
else:
    errors.append("docker-compose.test.yml missing")

# --- IF-V4-01 (b): resolved Keycloak healthcheck ---------------------------
kc = services.get("keycloak") or {}
kc_test = healthcheck_test_string(kc)
resolved = simulate_compose_interpolation(kc_test)
if "resp=$(cat <&3)" not in resolved:
    errors.append("keycloak healthcheck does not resolve to a shell "
                  "assignment 'resp=$(cat <&3)' after Compose "
                  f"interpolation (resolved: {resolved!r})")
echo_count = resolved.count('echo "$resp"')
if echo_count != 2:
    errors.append("keycloak healthcheck must resolve to exactly two "
                  "'echo \"$resp\"' references (one per grep); "
                  f"found {echo_count} in resolved: {resolved!r}")
if "grep -qE 'HTTP/1\\.[01] 200'" not in resolved:
    errors.append("keycloak healthcheck must require an HTTP 200 status "
                  "line in the discovery response (TCP alone is not healthy)")
if 'grep -q \'"issuer"\'' not in resolved:
    errors.append("keycloak healthcheck must require the \"issuer\" field "
                  "in the discovery body")
if "/realms/identityforge-lab/.well-known/openid-configuration" not in resolved:
    errors.append("keycloak healthcheck must probe the exact local realm "
                  "discovery URL")
if "127.0.0.1:8080" not in resolved:
    errors.append("keycloak healthcheck must probe the canonical loopback "
                  "address 127.0.0.1:8080")

# --- IF-V4-01: depends_on service_healthy wiring ---------------------------
for svc_name, dep_name in (("backend", "keycloak"), ("frontend", "backend")):
    svc = services.get(svc_name) or {}
    deps = svc.get("depends_on") or {}
    if isinstance(deps, list):
        errors.append(f"service {svc_name!r} uses list-style depends_on "
                      f"(cannot express service_healthy for {dep_name!r})")
        continue
    condition = (deps.get(dep_name) or {}).get("condition")
    if condition != "service_healthy":
        errors.append(f"service {svc_name!r} must declare depends_on "
                      f"{dep_name!r} with condition service_healthy "
                      f"(got {condition!r})")

if errors:
    for e in errors:
        print(f"FAIL: {e}")
    sys.exit(1)
print("PASS: docker-compose.yml parses; services keycloak/backend/frontend "
      "present; published ports locked to 127.0.0.1:8080/8000/5173; "
      "keycloak image pinned 26.8.2; no single-$ shell-variable trap in "
      "any healthcheck/command/entrypoint (IF-V4-01); resolved Keycloak "
      "healthcheck keeps literal '$resp' (2x) with HTTP-200 + issuer "
      "greps on the exact realm discovery URL; backend/frontend "
      "depends_on service_healthy verified (YAML-only check — "
      "`docker compose config` NOT RUN without Docker CLI)")
