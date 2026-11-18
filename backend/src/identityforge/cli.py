"""IdentityForge CLI.

Usage (from backend/):
    python -m identityforge.cli scenario I1
    python -m identityforge.cli verify-all
    python -m identityforge.cli doctor
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

# Allow running as `python -m identityforge.cli` from backend/ with src/ on path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from identityforge.config import get_settings  # noqa: E402
from identityforge.evidence.store import EvidenceStore  # noqa: E402
from identityforge.scenarios.definitions import BY_ID, get_definition  # noqa: E402
from identityforge.scenarios.engine import run_all, run_scenario  # noqa: E402


def _store() -> EvidenceStore:
    settings = get_settings()
    path = Path(settings.db_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return EvidenceStore(str(path))


def cmd_scenario(scenario_id: str) -> int:
    if get_definition(scenario_id) is None:
        print(f"unknown scenario: {scenario_id} (valid: {', '.join(BY_ID)})")
        return 2
    result = run_scenario(scenario_id, store=_store())
    print(f"[{result.scenario_id}] {result.title}")
    print(f"  mode:            {result.mode}")
    print(f"  status:          {result.status}")
    print(f"  expected:        {result.expected_outcome}")
    print(
        f"  secure:          {result.secure_result} ({result.secure_reason.value}) session={result.secure_session_created}"
    )
    print(f"  flawed fixture:  {result.flawed_result} session={result.flawed_session_created}")
    print(f"  resource access: {result.resource_access}")
    print(f"  run_id:          {result.run_id}  elapsed={result.elapsed_ms} ms")
    print(f"  limitations:     {result.limitations}")
    return 0 if result.status == "PASS" else 1


def cmd_verify_all() -> int:
    results = run_all(store=_store())
    print(f"{'ID':<4} {'STATUS':<6} {'SECURE':<16} {'REASON':<18} {'FLAWED':<10}")
    print("-" * 64)
    failed = 0
    for r in results:
        print(
            f"{r.scenario_id:<4} {r.status:<6} {r.secure_result:<16} {r.secure_reason.value:<18} {r.flawed_result:<10}"
        )
        if r.status != "PASS":
            failed += 1
    print("-" * 64)
    print(f"{len(results) - failed}/{len(results)} scenarios PASS")
    print("Mode: DETERMINISTIC OFFLINE FIXTURE — Keycloak NOT RUN here.")
    return 0 if failed == 0 else 1


def cmd_doctor() -> int:
    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Platform: {platform.platform()}")
    s = get_settings()
    print(f"Issuer: {s.issuer}")
    print(f"Client: {s.client_id}")
    print(f"Redirect: {s.redirect_uri}")
    print(f"Backend: {s.backend_host}:{s.backend_port} (loopback only)")
    print("Docker/Keycloak: NOT RUN in this sandbox — Compose is for reviewer machines.")
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import jwt  # noqa: F401

        print("Dependencies: fastapi, PyJWT, httpx import OK")
    except ImportError as exc:
        print(f"Dependencies MISSING: {exc}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="identityforge")
    sub = parser.add_subparsers(dest="command", required=True)
    p_scenario = sub.add_parser("scenario", help="Run one offline scenario, e.g. I1")
    p_scenario.add_argument("scenario_id")
    sub.add_parser("verify-all", help="Run I1–I18 offline and print a table")
    sub.add_parser("doctor", help="Environment check")
    args = parser.parse_args(argv)
    if args.command == "scenario":
        return cmd_scenario(args.scenario_id)
    if args.command == "verify-all":
        return cmd_verify_all()
    return cmd_doctor()


if __name__ == "__main__":
    raise SystemExit(main())
