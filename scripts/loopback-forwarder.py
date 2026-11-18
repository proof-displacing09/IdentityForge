#!/usr/bin/env python3
"""Stdlib-only loopback TCP forwarder (test-harness only, v8.0.3).

Usage:
    python3 loopback-forwarder.py <listen-host:port> <target-host:port>

Forwards every TCP connection accepted on the listen address to the
target address, byte-for-byte, in both directions. No protocol
awareness, no rewriting, no logging of payloads: it is a pure TCP
proxy, the Python equivalent of the socat forwarders the
frontend-e2e entrypoint starts (frontend/docker-e2e-entrypoint.sh).

Why this exists (scripts/test-all.ps1, gate LIVE_PROVIDER_PYTEST):
the four provider-dependent pytest tests (marked live_keycloak) build
their app from ``Settings()`` — pydantic field defaults, NOT env —
so the test app's IdP transport base is the loopback default
``http://127.0.0.1:8080`` and no ``-e
IDENTITYFORGE_IDP_TRANSPORT_BASE`` override can reroute it. Inside
the backend-test container, 127.0.0.1 is the container itself, so
without a listener there the discovery fetch fails and the tests
report 503 PROVIDER_UNAVAILABLE. This forwarder listens on the
container loopback (127.0.0.1:8080) and forwards to the cold-started
Keycloak service (``keycloak:8080``, resolvable on the disposable
project's Compose network). The backend still validates the
discovery issuer against the CANONICAL issuer
``http://127.0.0.1:8080/realms/identityforge-lab`` — the forwarder
changes only the network route, never the identity, exactly like
the shipped Compose transport route (keycloak:8080) and the e2e
socat forwarders. It is never imported by the backend, never
exposed as an endpoint, and runs only for the duration of the
LIVE_PROVIDER_PYTEST gate (the gate kills it and propagates
pytest's exit code).

Safety: binds ONLY the listen address given on the command line
(the gate passes 127.0.0.1:8080 — loopback inside the disposable
test container, never a public interface). Exits nonzero on a bad
address or when the listen socket cannot bind, so a failed
forwarder fails the gate instead of silently passing it.
"""

from __future__ import annotations

import socket
import sys
import threading


def _parse_hostport(spec: str) -> tuple[str, int]:
    if ":" not in spec:
        raise ValueError(f"expected host:port, got {spec!r}")
    host, _, port = spec.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"expected host:port, got {spec!r}")
    return host, int(port)


def _pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle(client: socket.socket, target_host: str, target_port: int) -> None:
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=10)
    except OSError as exc:
        print(f"loopback-forwarder: cannot reach {target_host}:{target_port}: {exc}",
              file=sys.stderr, flush=True)
        client.close()
        return
    t = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
    t.start()
    _pump(client, upstream)
    try:
        upstream.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    t.join(timeout=5)
    client.close()
    upstream.close()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: loopback-forwarder.py <listen-host:port> "
              "<target-host:port>", file=sys.stderr)
        return 2
    try:
        listen_host, listen_port = _parse_hostport(argv[1])
        target_host, target_port = _parse_hostport(argv[2])
    except ValueError as exc:
        print(f"loopback-forwarder: {exc}", file=sys.stderr)
        return 2
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((listen_host, listen_port))
    except OSError as exc:
        print(f"loopback-forwarder: cannot bind {listen_host}:{listen_port}: {exc}",
              file=sys.stderr)
        return 1
    server.listen(16)
    print(f"loopback-forwarder: listening {listen_host}:{listen_port} "
          f"-> {target_host}:{target_port}", file=sys.stderr, flush=True)
    try:
        while True:
            client, _addr = server.accept()
            threading.Thread(
                target=_handle, args=(client, target_host, target_port),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
