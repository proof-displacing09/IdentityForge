"""P1-09 (v3): production validator is closed; flawed code is offline-only.

Three proofs:
(a) ``inspect.signature(validate_id_token)`` has no ``omit`` parameter —
    there is no argument any caller could pass to skip a check.
(b) A fresh interpreter importing ``identityforge.api.app`` loads no
    module named ``validators_flawed`` or ``scenarios.flawed``. The
    check runs in a subprocess so the result cannot depend on what
    other tests imported first in this process.
(c) Static grep of ``backend/src/identityforge/api/`` for the word
    ``omit`` finds nothing — no call site in the live API can pass an
    omission to the validator.

The live callback's hard denial of a tampered signature is covered by
``test_tampered_id_token_via_callback_creates_no_session`` in
test_trustline_v2.py.
"""

from __future__ import annotations

import inspect
import os
import re
import subprocess
import sys
from pathlib import Path

from identityforge.protocol.validators import validate_id_token


def test_production_validator_has_no_omit_parameter():
    params = inspect.signature(validate_id_token).parameters
    assert "omit" not in params
    # And no other bypass-shaped parameter exists either.
    assert set(params) == {
        "token",
        "jwks",
        "expected_issuer",
        "expected_audience",
        "expected_nonce",
        "clock_skew_seconds",
        "now",
    }


def test_live_api_import_closure_excludes_flawed_modules(tmp_path):
    """Fresh interpreter: importing the API must not load flawed code."""
    src = Path(__file__).resolve().parents[2] / "src"
    probe = (
        "import sys\n"
        "import identityforge.api.app\n"
        "bad = sorted(m for m in sys.modules if 'flawed' in m)\n"
        "print('\\n'.join(bad))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    env["IDENTITYFORGE_DB_PATH"] = str(tmp_path / "closure.db")
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", f"flawed modules in API import closure: {proc.stdout}"


def test_no_omit_word_in_live_api_sources():
    """Static guard: the live API package must not mention 'omit' at all."""
    api_dir = Path(__file__).resolve().parents[2] / "src" / "identityforge" / "api"
    pattern = re.compile(r"\bomit\b")
    hits = []
    for path in sorted(api_dir.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not hits, f"'omit' found in live API sources: {hits}"
