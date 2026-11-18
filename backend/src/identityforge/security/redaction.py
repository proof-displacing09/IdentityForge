"""Redaction and tamper-evident evidence hashing (I17, evidence integrity).

Rules:
- Never log or store raw tokens, codes, verifiers, nonces, secrets,
  cookies or passwords. Replace them with a short fingerprint
  (first 8 hex chars of SHA-256) or the literal "[REDACTED]".
- Strip CR/LF from log values so a crafted username cannot forge log lines.
- Canonical JSON (sorted keys, compact separators) hashed with SHA-256
  gives an integrity fingerprint for a report — it proves the artifact
  has not changed since it was written, not that its contents are true.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SENSITIVE_KEYS = {
    "access_token",
    "id_token",
    "refresh_token",
    "code",
    "code_verifier",
    "code_challenge",
    "nonce",
    "state",
    "client_secret",
    "password",
    "session",
    "session_id",
    "cookie",
    "authorization",
    "token",
    "secret",
    "csrf",
    "csrf_token",
}
_TOKEN_LIKE = re.compile(r"(?i)(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})")


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def sanitize_log_value(value: str) -> str:
    """Remove CR/LF (log injection) and truncate overlong values."""
    cleaned = value.replace("\r", "\\r").replace("\n", "\\n")
    return cleaned[:500]


def redact_value(key: str, value: Any) -> Any:
    if isinstance(value, str) and key.lower() in SENSITIVE_KEYS:
        return f"[REDACTED:{fingerprint(value)}]" if value else "[REDACTED]"
    if isinstance(value, dict):
        return redact_dict(value)
    if isinstance(value, list):
        return [redact_value(key, v) for v in value]
    if isinstance(value, str):
        redacted = _TOKEN_LIKE.sub("[REDACTED-TOKEN]", value)
        return sanitize_log_value(redacted)
    return value


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {str(k): redact_value(str(k), v) for k, v in data.items()}


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def canonical_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
