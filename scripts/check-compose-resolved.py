#!/usr/bin/env python3
"""Validate the actual Keycloak healthcheck in `docker compose config --format json`.

Consume JSON via stdin (never print or persist it; rendered environment may
include credentials). Compose can re-escape literal '$' as '$$' for a
re-parseable config output. Normalize only that display escaping before
checking the exact shell-level healthcheck contract.

Fails closed on invalid JSON, wrong service, absent shell assignment, missing
HTTP/200 or issuer check, or missing `$resp` references. No Docker daemon
or additional Python packages required by this validator.
"""
import json
import sys


def validate(model: dict) -> list[str]:
    problems = []
    try:
        test = model["services"]["keycloak"]["healthcheck"]["test"]
    except (KeyError, TypeError):
        return ["keycloak.healthcheck.test is missing"]
    if not (isinstance(test, list) and len(test) == 4 and
            test[:3] == ["CMD", "bash", "-c"] and isinstance(test[3], str)):
        return ["keycloak healthcheck must use CMD bash -c with one shell command"]

    # Compose may render a re-parseable config with doubled dollar signs.
    # This does NOT permit an absent $resp; such a value will still fail.
    command = test[3].replace("$$", "$")
    if "exec 3<>/dev/tcp/127.0.0.1/8080" not in command:
        problems.append("Keycloak loopback readiness TCP probe missing")
    if "GET /realms/identityforge-lab/.well-known/openid-configuration HTTP/1.1" not in command:
        problems.append("canonical discovery URL missing")
    if "resp=$(cat <&3)" not in command:
        problems.append("healthcheck response assignment missing")
    if command.count('echo "$resp"') != 2:
        problems.append("expected exactly two literal echo \"$resp\" references")
    if "grep -qE 'HTTP/1\\.[01] 200'" not in command:
        problems.append("strict HTTP 200 status check missing")
    if "grep -q '\"issuer\"'" not in command:
        problems.append("issuer field check missing")
    return problems


def main() -> int:
    try:
        model = json.load(sys.stdin)
        if not isinstance(model, dict):
            raise ValueError("root must be an object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: invalid docker compose config JSON ({type(exc).__name__})", file=sys.stderr)
        return 1
    problems = validate(model)
    if problems:
        for message in problems:
            print(f"FAIL: COMPOSE_CONFIG: {message}", file=sys.stderr)
        return 1
    print("PASS: Keycloak resolved healthcheck retains response, HTTP 200 and issuer checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
