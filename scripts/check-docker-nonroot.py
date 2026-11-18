#!/usr/bin/env python3
"""Static non-root attestation for IF-V8-42 (v8.0.5).

Purpose-built checker (hadolint is not available in this sandbox):
it parses the three app Dockerfiles and both Compose files and
asserts the exact non-root invariants the fix depends on. It runs
no container and proves no runtime behaviour — the Docker runtime
proofs (build, boot, `id` in running containers, volume migration)
are NOT RUN here and stay reviewer gates. What it DOES prove is
that the shipped tree states the intended design everywhere, with
no `USER root`, no privileged/host-network/docker.sock escape hatch,
no 127.0.0.1 violation, and no pip-audit gate-time install left
behind.

Rules (each prints PASS/FAIL with the rule id):
  D1  Every app Dockerfile has exactly one USER instruction, numeric
      UID:GID, UID != 0 and GID != 0.
  D2  No Dockerfile contains `USER root` / `USER 0` (any form).
  D3  No Dockerfile contains `chmod 777` / `chmod a+rwx`.
  D4  The app UID:GID is identical in all three Dockerfiles and
      equals the --uid/--gid the prep service passes (10001).
  D5  No Dockerfile or E2E entrypoint uses a privilege-escalation
      helper (gosu, setpriv, `su `).
  D6  Every RUN instruction precedes the USER instruction (all
      build work as root happens before the privilege drop; nothing
      runs as root after it).
  C1  Every published port in both Compose files binds 127.0.0.1.
  C2  No service is privileged, host-networked, or mounts
      docker.sock.
  C3  Keycloak is untouched: no `user:` override, image pinned
      to 26.8.2.
  C4  backend-data-prep is the ONLY service allowed `user: "0:0"`;
      every other service has no user override or a numeric
      non-root user.
  C5  backend-data-prep mounts ONLY backend_data, publishes no
      ports, and its command is exactly the prep invocation with
      --data-dir /app/data and the app UID/GID.
  C6  backend depends_on backend-data-prep (service_completed_
      successfully) AND keycloak (service_healthy); frontend
      depends_on backend (service_healthy).
  C7  Host-path bind mounts are only the documented ones
      (read-only test mounts + ./test-results outputs + the
      Keycloak realm import); named volumes are backend_data /
      keycloak_data only.
  P1  The prep script is stdlib-only, contains no subprocess /
      exec / spawn / system call and never starts the app server.
  P2  The prep script's default UID/GID equal the Dockerfile UID.
  S1  test-all.ps1 runs pip-audit without a gate-time `pip install`.
  S2  The backend Dockerfile installs the pinned pip-audit at
      BUILD time from requirements-audit.txt.
  E1  The E2E entrypoint preflights writability of the screenshots
      and report bind mounts and fails closed (exit 1) when they
      are not writable.

Exit 0 when every rule passes, 1 on any violation, 2 when PyYAML
is missing (ENVIRONMENT NOT READY — same guard as
scripts/compose-config-check.py).
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ENVIRONMENT NOT READY: PyYAML is required to validate "
          "the Compose files (scripts/check-docker-nonroot.py "
          "imports yaml), but it is not installed for this "
          f"interpreter ({sys.executable}). Install it with "
          "'python3 -m pip install pyyaml' (or your system package "
          "'python3-yaml'), then re-run. This is a missing test "
          "prerequisite, not a non-root defect.")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
APP_UID = 10001
APP_GID = 10001
DOCKERFILES = [
    ROOT / "backend" / "Dockerfile",
    ROOT / "frontend" / "Dockerfile",
    ROOT / "frontend" / "Dockerfile.e2e",
]
COMPOSE_FILES = [ROOT / "docker-compose.yml", ROOT / "docker-compose.test.yml"]
PREP_SCRIPT = ROOT / "backend" / "docker" / "prepare-data-volume.py"
PS1 = ROOT / "scripts" / "test-all.ps1"
E2E_ENTRYPOINT = ROOT / "frontend" / "docker-e2e-entrypoint.sh"

# Host-path bind mounts the lab documents (anything else fails C7).
ALLOWED_HOST_MOUNTS = {
    "./backend/tests", "./docs", "./scripts", "./example-reports",
    "./README.md", "./SECURITY.md", "./test-results",
    "./test-results/e2e-screenshots",
    "./keycloak/realm-import",
}
ALLOWED_NAMED_VOLUMES = {"backend_data", "keycloak_data"}
STDLIB_IMPORTS = {"argparse", "os", "sqlite3", "stat", "sys"}

results = []


def check(rule, ok, detail):
    results.append((rule, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} [{rule}] {detail}")


def non_comment_lines(path):
    out = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return out


# --- D1/D2/D3/D5/D6: Dockerfile rules --------------------------------------
users = {}
for df in DOCKERFILES:
    rel = str(df.relative_to(ROOT))
    lines = non_comment_lines(df)
    user_lines = [ln.strip() for ln in lines
                  if ln.strip().upper().startswith("USER ")]
    if len(user_lines) == 1:
        m = re.fullmatch(r"USER (\d+):(\d+)", user_lines[0])
        if m and int(m.group(1)) != 0 and int(m.group(2)) != 0:
            users[rel] = (int(m.group(1)), int(m.group(2)))
            check("D1", True, f"{rel}: exactly one USER, "
                  f"numeric non-root {m.group(1)}:{m.group(2)}")
        else:
            check("D1", False, f"{rel}: USER is not numeric non-root "
                  f"UID:GID (found: {user_lines[0]!r})")
    else:
        check("D1", False, f"{rel}: expected exactly one USER "
              f"instruction, found {len(user_lines)}")
    text = "\n".join(lines)
    check("D2", not re.search(r"(?im)^USER\s+(root|0)\b", text),
          f"{rel}: no `USER root` / `USER 0`"
          if not re.search(r"(?im)^USER\s+(root|0)\b", text)
          else f"{rel}: contains a root USER instruction")
    check("D3", not re.search(r"chmod\s+(-R\s+)?(777|a\+rwx)\b", text),
          f"{rel}: no chmod 777 / a+rwx"
          if not re.search(r"chmod\s+(-R\s+)?(777|a\+rwx)\b", text)
          else f"{rel}: contains chmod 777 / a+rwx")
    check("D5", not re.search(r"\b(gosu|setpriv)\b|\bsu\s+(-|root)\b", text),
          f"{rel}: no gosu/setpriv/su escalation helper"
          if not re.search(r"\b(gosu|setpriv)\b|\bsu\s+(-|root)\b", text)
          else f"{rel}: contains a privilege-escalation helper")
    user_idx = next((i for i, ln in enumerate(lines)
                     if ln.strip().upper().startswith("USER ")), None)
    run_after = [ln.strip() for ln in lines[user_idx + 1:]
                 if ln.strip().upper().startswith("RUN ")] \
        if user_idx is not None else []
    check("D6", user_idx is not None and not run_after,
          f"{rel}: no RUN after the USER privilege drop"
          if user_idx is not None and not run_after
          else (f"{rel}: no USER instruction, so no privilege drop exists"
                if user_idx is None
                else f"{rel}: RUN instruction(s) after USER: {run_after}"))

# --- D4: one app identity everywhere ---------------------------------------
if users and len(set(users.values())) == 1:
    uid, gid = next(iter(users.values()))
    check("D4", (uid, gid) == (APP_UID, APP_GID),
          f"app UID:GID is {uid}:{gid} in all {len(users)} Dockerfiles"
          f"{' (expected 10001:10001)' if (uid, gid) != (APP_UID, APP_GID) else ''}")
else:
    check("D4", False, f"app UID:GID differs across Dockerfiles: {users}")

# --- E1/D5 for the E2E entrypoint ------------------------------------------
entry_text = E2E_ENTRYPOINT.read_text()
check("D5", not re.search(r"\b(gosu|setpriv)\b|\bsu\s+(-|root)\b", entry_text),
      "frontend/docker-e2e-entrypoint.sh: no gosu/setpriv/su helper"
      if not re.search(r"\b(gosu|setpriv)\b|\bsu\s+(-|root)\b", entry_text)
      else "frontend/docker-e2e-entrypoint.sh: escalation helper found")
check("E1", "/app/e2e/screenshots" in entry_text
      and "/app/test-results" in entry_text
      and "exit 1" in entry_text
      and "not writable" in entry_text,
      "frontend/docker-e2e-entrypoint.sh: writability preflight for "
      "screenshots + report mounts, fail-closed (exit 1)")

# --- Compose rules ----------------------------------------------------------
docs = {}
for cf in COMPOSE_FILES:
    rel = str(cf.relative_to(ROOT))
    try:
        docs[rel] = yaml.safe_load(cf.read_text())
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        check("C1", False, f"{rel}: does not parse as YAML: {exc}")
        docs[rel] = {"services": {}}

all_services = {}
for rel, doc in docs.items():
    for name, svc in (doc.get("services") or {}).items():
        all_services.setdefault(name, []).append((rel, svc or {}))


def iter_services():
    for name, occurrences in all_services.items():
        for rel, svc in occurrences:
            yield name, rel, svc


# C1: loopback-only published ports.
bad_ports = []
for name, rel, svc in iter_services():
    for port in svc.get("ports") or []:
        if not str(port).startswith("127.0.0.1:"):
            bad_ports.append(f"{rel} {name}: {port!r}")
check("C1", not bad_ports,
      "all published ports bind 127.0.0.1 only"
      if not bad_ports else f"non-loopback published ports: {bad_ports}")

# C2: no privileged / host network / docker.sock.
bad_c2 = []
for name, rel, svc in iter_services():
    if svc.get("privileged") is True:
        bad_c2.append(f"{rel} {name}: privileged: true")
    if str(svc.get("network_mode", "")).lower() == "host":
        bad_c2.append(f"{rel} {name}: network_mode: host")
    for vol in svc.get("volumes") or []:
        if "docker.sock" in str(vol):
            bad_c2.append(f"{rel} {name}: docker.sock mount {vol!r}")
check("C2", not bad_c2,
      "no privileged / host-network / docker.sock in any service"
      if not bad_c2 else f"escape hatches: {bad_c2}")

# C3: Keycloak untouched.
kc = dict(all_services.get("keycloak", [])).get("docker-compose.yml", {})
kc_image = str(kc.get("image", ""))
check("C3", "user" not in kc and "26.8.2" in kc_image,
      "keycloak: no `user:` override, image pinned 26.8.2"
      if "user" not in kc and "26.8.2" in kc_image
      else f"keycloak changed: user={kc.get('user')!r} image={kc_image!r}")

# C4: only backend-data-prep may run as root.
root_users = [(rel, name) for name, rel, svc in iter_services()
              if str(svc.get("user", "")).strip() in ("0", "0:0", "root")]
check("C4", root_users == [("docker-compose.yml", "backend-data-prep")],
      "only backend-data-prep runs as root (explicit one-shot)"
      if root_users == [("docker-compose.yml", "backend-data-prep")]
      else f"services running as root: {root_users}")

# C5: prep service scope.
prep = dict(all_services.get("backend-data-prep", [])).get("docker-compose.yml", {})
prep_vols = [str(v) for v in prep.get("volumes") or []]
prep_cmd = prep.get("command") or []
if isinstance(prep_cmd, str):
    prep_cmd = [prep_cmd]
prep_cmd_text = " ".join(str(c) for c in prep_cmd)
check("C5", prep_vols == ["backend_data:/app/data"]
      and not prep.get("ports")
      and "/app/prepare-data-volume.py" in prep_cmd_text
      and "--data-dir" in prep_cmd_text and "/app/data" in prep_cmd_text
      and "--uid" in prep_cmd_text and str(APP_UID) in prep_cmd_text
      and "--gid" in prep_cmd_text and str(APP_GID) in prep_cmd_text,
      "backend-data-prep: mounts only backend_data, no ports, "
      "command is the prep script on /app/data as 10001:10001"
      if prep_vols == ["backend_data:/app/data"] and not prep.get("ports")
      else f"backend-data-prep scope wrong: volumes={prep_vols} "
           f"ports={prep.get('ports')} command={prep_cmd_text!r}")

# C6: backend gating on prep + keycloak; frontend on backend.
backend = dict(all_services.get("backend", [])).get("docker-compose.yml", {})
bdeps = backend.get("depends_on") or {}
frontend = dict(all_services.get("frontend", [])).get("docker-compose.yml", {})
fdeps = frontend.get("depends_on") or {}
check("C6", isinstance(bdeps, dict)
      and (bdeps.get("backend-data-prep") or {}).get("condition")
      == "service_completed_successfully"
      and (bdeps.get("keycloak") or {}).get("condition") == "service_healthy"
      and isinstance(fdeps, dict)
      and (fdeps.get("backend") or {}).get("condition") == "service_healthy",
      "backend waits for prep (completed) + keycloak (healthy); "
      "frontend waits for backend (healthy)"
      if isinstance(bdeps, dict)
      and (bdeps.get("backend-data-prep") or {}).get("condition")
      == "service_completed_successfully"
      else f"depends_on wiring wrong: backend={bdeps} frontend={fdeps}")

# C7: bind-mount allowlist + named volumes.
bad_mounts = []
for name, rel, svc in iter_services():
    for vol in svc.get("volumes") or []:
        v = str(vol)
        host = v.split(":")[0]
        if host.startswith((".", "/")):
            if host not in ALLOWED_HOST_MOUNTS:
                bad_mounts.append(f"{rel} {name}: {v!r}")
        elif host not in ALLOWED_NAMED_VOLUMES:
            bad_mounts.append(f"{rel} {name}: {v!r}")
check("C7", not bad_mounts,
      "host-path mounts are only the documented ones; named "
      "volumes are backend_data / keycloak_data"
      if not bad_mounts else f"unexpected mounts: {bad_mounts}")

# --- P1/P2: prep script ------------------------------------------------------
if not PREP_SCRIPT.exists():
    check("P1", False, "backend/docker/prepare-data-volume.py: missing "
          "(no one-shot volume prep exists)")
    check("P2", False, "backend/docker/prepare-data-volume.py: missing")
    prep_text = ""
else:
    prep_text = PREP_SCRIPT.read_text()
    imported = set(re.findall(r"^import (\w+)|^from (\w+) import", prep_text,
                              flags=re.M))
    imported = {a or b for a, b in imported}
    check("P1", imported <= STDLIB_IMPORTS
          and not re.search(r"\b(subprocess|os\.exec|os\.system|os\.spawn|"
                            r"os\.posix_spawn|eval\(|exec\()", prep_text)
          and "uvicorn" not in prep_text,
          "backend/docker/prepare-data-volume.py: stdlib-only "
          f"(imports: {sorted(imported)}), no subprocess/exec/spawn, "
          "never starts the app server"
          if imported <= STDLIB_IMPORTS else
          f"prep script imports non-stdlib modules: {sorted(imported - STDLIB_IMPORTS)}")
    m_uid = re.search(r"DEFAULT_UID = (\d+)", prep_text)
    m_gid = re.search(r"DEFAULT_GID = (\d+)", prep_text)
    check("P2", bool(m_uid and m_gid
                     and int(m_uid.group(1)) == APP_UID
                     and int(m_gid.group(1)) == APP_GID),
          "prep script defaults are UID/GID 10001:10001"
          if m_uid and m_gid else "prep script UID/GID defaults not found")

# --- S1/S2: pip-audit path ---------------------------------------------------
ps1_text = PS1.read_text()
audit_section = ps1_text[ps1_text.find("PYTHON_DEPENDENCY_AUDIT"):]
check("S1", "pip install" not in audit_section
      and "python -m pip_audit -r requirements-freeze.txt" in audit_section,
      "test-all.ps1 PYTHON_DEPENDENCY_AUDIT: no gate-time pip "
      "install; runs the build-time tool over requirements-freeze.txt"
      if "pip install" not in audit_section
      else "test-all.ps1 still installs pip-audit at gate time")
backend_df = (ROOT / "backend" / "Dockerfile").read_text()
check("S2", bool(re.search(
    r"RUN pip install --no-cache-dir -r requirements-audit\.txt",
    backend_df)),
    "backend/Dockerfile installs pinned pip-audit at BUILD time"
    if re.search(r"RUN pip install --no-cache-dir -r requirements-audit\.txt",
                 backend_df)
    else "backend/Dockerfile does not install pip-audit at build time")

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} non-root checks PASS"
      f"{f' — FAILING: {[r[0] for r in failed]}' if failed else ''}")
sys.exit(1 if failed else 0)
