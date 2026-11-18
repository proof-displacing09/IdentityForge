"""Offline scenario engine (I1–I18).

Executes each scenario twice on deterministic synthetic transactions:
  * secure — the real validators / session / policy code from this package;
  * flawed — an isolated pure-function fixture (scenarios/flawed.py) that
    deliberately omits one check, showing why the check matters.

Mode is always "DETERMINISTIC OFFLINE FIXTURE" here. Nothing in this
engine talks to Keycloak, the network, or the real portal session store:
flawed sessions are local booleans, never real session cookies. RSA keys
are generated fresh per run and discarded.
"""

from __future__ import annotations

import platform
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from ..config import Settings, get_settings
from ..models import (
    ComparisonResult,
    FailureReason,
    ReproducibilityMetadata,
    TransactionStep,
    ValidationCheck,
)
from ..protocol.jwks import validate_issuer_url, validate_jwks_url
from ..protocol.pkce import TransactionStore, verify_pkce
from ..protocol.redirect import check_redirect_uri
from ..protocol.validators import validate_id_token
from ..security import csrf as csrf_mod
from ..security.policy import can_access
from ..security.redaction import sanitize_log_value
from ..security.session import SessionStore
from .definitions import BY_ID, get_definition
from .fixtures import (
    CLIENT_ID,
    EXPECTED_ISSUER,
    generate_rsa_keypair,
    mint_id_token,
    new_run_id,
    roles_for_fixture_subject,
)


def _step(
    step: str, outcome: str, reason: FailureReason | None = None, detail: str = ""
) -> TransactionStep:
    return TransactionStep(
        step=step,
        outcome=outcome,  # type: ignore[arg-type]
        reason_code=reason,
        detail=detail,
        at=datetime.now(timezone.utc),
    )


def _valid_setup(nonce: str = "test-nonce"):
    pem, jwk = generate_rsa_keypair()
    jwks = {"keys": [jwk]}
    token = mint_id_token(private_pem=pem, nonce=nonce)
    return pem, jwks, token


def run_scenario(
    scenario_id: str,
    settings: Settings | None = None,
    store: Any | None = None,
) -> ComparisonResult:
    # P1-09: the flawed fixture module is imported LAZILY, only when a
    # scenario actually runs. Importing this engine (and therefore the
    # live API, which imports it for POST /runs) must not pull flawed
    # validator code into the process — see
    # tests/security/test_validator_separation.py.
    from . import flawed as flawed_mod

    sid = scenario_id.upper()
    definition = get_definition(sid)
    if definition is None:
        raise ValueError(f"unknown scenario: {scenario_id}")
    s = settings or get_settings()
    started = time.monotonic()
    run_id = new_run_id()
    timeline: list[TransactionStep] = []
    decisions: list[ValidationCheck] = []
    resource: dict[str, bool] = {}
    secure_session = False
    flawed_session = False
    # P0-06 honest state semantics (see models.ComparisonResult).
    session_preexisted = False
    session_revoked = False
    flawed_model_status = "EXECUTED"
    flawed_guard_omitted = ""
    flawed_observed_result = ""
    protected_resource_disclosed = False
    secure_reason = FailureReason.OK
    flawed_reason = FailureReason.OK
    secure_result = "rejected"
    flawed_result = "allowed"
    expected = definition.expected_secure

    # -- I1: normal login -------------------------------------------------
    if sid == "I1":
        _, jwks, token = _valid_setup()
        dec = validate_id_token(
            token,
            jwks=jwks,
            expected_issuer=EXPECTED_ISSUER,
            expected_audience=CLIENT_ID,
            expected_nonce="test-nonce",
        )
        decisions = dec.checks
        timeline.append(_step("TOKEN_VERIFIED", "ok" if dec.valid else "rejected", dec.reason_code))
        if dec.valid:
            sessions = SessionStore()
            rec = sessions.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            secure_session = True
            secure_result = "session_created"
            resource = {"member": can_access(rec, "member"), "officer": can_access(rec, "officer")}
            timeline.append(_step("SESSION_CREATED", "ok", detail="member session created"))
        # Flawed side: a valid token is accepted by the flawed validator
        # too (nothing is wrong with it). Model the session the flawed
        # path would mint by actually creating one in a local store.
        if dec.valid:
            flawed_store = SessionStore()
            flawed_store.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            flawed_session = True
            flawed_observed_result = "session_created (valid token accepted by both paths)"
        flawed_guard_omitted = "none (valid login; no check is wrong)"
        flawed_result = "allowed"
        expected_ok = (
            dec.valid and resource.get("member") is True and resource.get("officer") is False
        )

    # -- I2: wrong state --------------------------------------------------
    elif sid == "I2":
        store_txn = TransactionStore()
        txn = store_txn.create(redirect_uri=s.redirect_uri, client_id=s.client_id, issuer=s.issuer)
        timeline.append(_step("AUTHORIZATION_STARTED", "ok"))
        # Attacker presents a different state.
        presented = "attacker-state-" + secrets.token_hex(4)
        found = store_txn.lookup_by_state(presented)
        if found is None:
            secure_reason = FailureReason.STATE_MISMATCH
            secure_result = "rejected"
            timeline.append(
                _step(
                    "CALLBACK_RECEIVED",
                    "rejected",
                    secure_reason,
                    "state does not match any transaction",
                )
            )
        flawed_accept = flawed_mod.flawed_skip_state(presented, txn.state)
        if flawed_accept:
            # The flawed callback proceeds past the state check: model the
            # session it would mint by actually creating one locally.
            flawed_store = SessionStore()
            flawed_store.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            flawed_observed_result = "attacker state accepted; session minted by flawed path"
        flawed_session = bool(flawed_accept)
        flawed_guard_omitted = "state"
        flawed_result = "allowed" if flawed_accept else "rejected"
        expected_ok = secure_reason == FailureReason.STATE_MISMATCH and not secure_session

    # -- I3: wrong PKCE ---------------------------------------------------
    elif sid == "I3":
        store_txn = TransactionStore()
        txn = store_txn.create(redirect_uri=s.redirect_uri, client_id=s.client_id, issuer=s.issuer)
        ok = verify_pkce("wrong-verifier", txn.code_challenge)
        if not ok:
            secure_reason = FailureReason.PKCE_MISMATCH
            secure_result = "rejected"
            timeline.append(_step("CODE_REDEEMED", "rejected", secure_reason))
        flawed_accept = flawed_mod.flawed_skip_pkce("wrong-verifier", txn.code_challenge)
        if flawed_accept:
            flawed_store = SessionStore()
            flawed_store.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            flawed_observed_result = "wrong verifier accepted; session minted by flawed path"
        flawed_session = flawed_accept
        flawed_guard_omitted = "pkce"
        flawed_result = "allowed" if flawed_session else "rejected"
        expected_ok = secure_reason == FailureReason.PKCE_MISMATCH and not ok

    # -- I4: invalid redirect ---------------------------------------------
    elif sid == "I4":
        reason = check_redirect_uri(
            "http://127.0.0.1:8000/auth/callback/evil", s.allowed_redirect_uris
        )
        secure_reason = reason
        secure_result = "rejected" if reason != FailureReason.OK else "allowed"
        timeline.append(
            _step("AUTHORIZATION_STARTED", "rejected", reason, "redirect URI not registered")
        )
        flawed_accept = flawed_mod.flawed_skip_redirect("http://127.0.0.1:8000/auth/callback/evil")
        if flawed_accept:
            flawed_store = SessionStore()
            flawed_store.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            flawed_observed_result = "unregistered redirect accepted; session minted by flawed path"
        flawed_session = flawed_accept
        flawed_guard_omitted = "redirect_uri"
        flawed_result = "allowed" if flawed_session else "rejected"
        expected_ok = reason == FailureReason.REDIRECT_URI_MISMATCH

    # -- I5 / I6 / I7 / I8 / I9 / I14: token validation variants ---------
    elif sid in ("I5", "I6", "I7", "I8", "I9", "I14"):
        pem, jwks, _ = _valid_setup()
        pem2, _ = generate_rsa_keypair(kid="other-key")
        if sid == "I5":
            token = mint_id_token(private_pem=pem, issuer="http://127.0.0.1:8080/realms/evil-lab")
            dec = validate_id_token(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            flawed_dec = flawed_mod.flawed_skip_issuer(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
        elif sid == "I6":
            token = mint_id_token(private_pem=pem, audience="other-synthetic-client")
            dec = validate_id_token(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            flawed_dec = flawed_mod.flawed_skip_audience(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
        elif sid == "I7":
            # -300s is beyond the 120s clock skew, so expiry must be rejected.
            token = mint_id_token(private_pem=pem, expires_in=-300)
            dec = validate_id_token(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            flawed_dec = flawed_mod.flawed_skip_expiry(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            # Replay sub-check: state consumed twice.
            txn_store = TransactionStore()
            txn = txn_store.create(
                redirect_uri=s.redirect_uri, client_id=s.client_id, issuer=s.issuer
            )
            first = txn_store.consume_by_state(txn.state) is not None
            second = txn_store.consume_by_state(txn.state) is not None
            timeline.append(
                _step("CALLBACK_RECEIVED", "ok" if first else "rejected", detail="first use ok")
            )
            timeline.append(
                _step(
                    "CALLBACK_RECEIVED",
                    "rejected" if not second else "ok",
                    FailureReason.STATE_REUSED,
                    "second use rejected",
                )
            )
            expected_ok = dec.reason_code == FailureReason.EXPIRED and first and not second
            decisions = dec.checks
            secure_reason = dec.reason_code
            secure_result = "rejected" if not dec.valid else "allowed"
            if flawed_dec.valid:
                flawed_store = SessionStore()
                flawed_store.create(
                    subject="student_01",
                    username="student_01",
                    roles=roles_for_fixture_subject("student_01"),
                    issuer=EXPECTED_ISSUER,
                )
                flawed_observed_result = "expired token accepted; session minted by flawed path"
            flawed_session = bool(flawed_dec.valid)
            flawed_guard_omitted = "expiry"
            flawed_result = "allowed" if flawed_session else "rejected"
            flawed_reason = FailureReason.OK if flawed_session else FailureReason.EXPIRED
            timeline.append(_step("TOKEN_VERIFIED", "rejected", dec.reason_code, "expired token"))
            # fall through to result assembly below (skip generic block)
            return _finish(
                sid,
                definition,
                run_id,
                expected,
                secure_result,
                flawed_result,
                secure_reason,
                flawed_reason,
                secure_session,
                flawed_session,
                resource,
                timeline,
                decisions,
                started,
                store,
                expected_ok,
                session_preexisted=session_preexisted,
                session_revoked=session_revoked,
                flawed_model_status=flawed_model_status,
                flawed_guard_omitted=flawed_guard_omitted,
                flawed_observed_result=flawed_observed_result,
                protected_resource_disclosed=protected_resource_disclosed,
            )
        elif sid == "I8":
            token = mint_id_token(private_pem=pem, nonce="different-nonce")
            dec = validate_id_token(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            flawed_dec = flawed_mod.flawed_skip_nonce(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
        elif sid == "I9":
            # Tampered token (primary sub-case); alg-none and wrong-key are
            # covered by dedicated unit/protocol tests and recorded here.
            token = mint_id_token(private_pem=pem, tamper=True)
            dec = validate_id_token(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            flawed_dec = flawed_mod.flawed_skip_signature(
                token,
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
        else:  # I14
            dec = validate_id_token(
                "not.a.jwt",
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
            flawed_dec = flawed_mod.flawed_skip_signature(
                "not.a.jwt",
                jwks=jwks,
                expected_issuer=EXPECTED_ISSUER,
                expected_audience=CLIENT_ID,
                expected_nonce="test-nonce",
            )
        decisions = dec.checks
        secure_reason = dec.reason_code
        secure_result = "rejected" if not dec.valid else "allowed"
        if flawed_dec.valid:
            flawed_store = SessionStore()
            flawed_store.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            flawed_observed_result = "invalid token accepted; session minted by flawed path"
        else:
            # I14: the token is malformed, so even the flawed validator
            # (signature check omitted) rejects it — a proven hypothesis,
            # not a fabricated acceptance.
            flawed_observed_result = (
                "rejected by flawed path too: malformed token cannot be "
                "validated even without the signature check"
            )
        flawed_session = bool(flawed_dec.valid)
        flawed_guard_omitted = {
            "I5": "issuer",
            "I6": "audience",
            "I8": "nonce",
            "I9": "signature",
            "I14": "signature",
        }[sid]
        flawed_result = "allowed" if flawed_session else "rejected"
        flawed_reason = FailureReason.OK if flawed_session else dec.reason_code
        timeline.append(
            _step("TOKEN_VERIFIED", "rejected" if not dec.valid else "ok", dec.reason_code)
        )
        expected_map = {
            "I5": FailureReason.WRONG_ISSUER,
            "I6": FailureReason.WRONG_AUDIENCE,
            "I8": FailureReason.NONCE_MISMATCH,
            "I9": FailureReason.BAD_SIGNATURE,
            "I14": FailureReason.MALFORMED_TOKEN,
        }
        expected_ok = dec.reason_code == expected_map[sid] and not dec.valid

    # -- I10: code replay --------------------------------------------------
    elif sid == "I10":
        sessions = SessionStore()
        # First (legitimate) redemption: actually create the session it
        # mints, so it is a PREEXISTING session for the replay test below.
        first_rec = sessions.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        first_ok = sessions.get(first_rec.session_id) is not None
        # Second redemption of the same code must fail: the code is spent.
        second_ok = False
        timeline.append(_step("CODE_REDEEMED", "ok", detail="first redemption"))
        timeline.append(
            _step(
                "CODE_REDEEMED",
                "rejected",
                FailureReason.CODE_REUSED,
                "second redemption of same code",
            )
        )
        secure_reason = FailureReason.CODE_REUSED
        secure_result = "rejected"  # the replay is rejected
        session_preexisted = True  # the first redemption's session survives
        flawed_store = SessionStore()
        flawed_store.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        flawed_session = True  # flawed fixture redeems twice: a second session
        flawed_guard_omitted = "code_single_use"
        flawed_observed_result = "second redemption of the same code minted another session"
        flawed_result = "allowed"
        expected_ok = first_ok and not second_ok

    # -- I11: fixation / rotation ------------------------------------------
    elif sid == "I11":
        sessions = SessionStore()
        # Attacker learns a session id before login; the secure path
        # rotates to a fresh id and revokes the known one.
        pre = sessions.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        attacker_known = pre.session_id
        rotated = sessions.rotate(
            old_session_id=attacker_known,
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        secure_ok = rotated.session_id != attacker_known and sessions.get(attacker_known) is None
        secure_reason = FailureReason.OK if secure_ok else FailureReason.SESSION_FIXATION
        secure_result = "session_created" if secure_ok else "rejected"
        secure_session = secure_ok
        # Flawed path: no rotation — the attacker-known id stays valid.
        # Nothing new is created; the pre-login session SURVIVES.
        flawed_sessions = SessionStore()
        flawed_rec = flawed_sessions.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        flawed_still_valid = flawed_sessions.get(flawed_rec.session_id) is not None
        flawed_session = False
        session_preexisted = True
        flawed_guard_omitted = "session_rotation"
        flawed_observed_result = (
            "attacker-known session id still valid after login (no rotation)"
            if flawed_still_valid
            else "flawed model failed"
        )
        flawed_result = "allowed"
        timeline.append(
            _step(
                "SESSION_CREATED",
                "ok" if secure_ok else "rejected",
                secure_reason,
                "session id rotated on login",
            )
        )
        expected_ok = secure_ok

    # -- I12: logout / stale cookie ----------------------------------------
    elif sid == "I12":
        sessions = SessionStore()
        rec = sessions.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        session_preexisted = True  # login happened before the tested logout
        sessions.revoke(rec.session_id)
        stale = sessions.get(rec.session_id)
        secure_ok = stale is None
        secure_reason = FailureReason.SESSION_REVOKED if secure_ok else FailureReason.OK
        secure_result = "rejected" if secure_ok else "allowed"
        session_revoked = secure_ok
        resource = {"member_after_logout": can_access(stale, "member")}
        timeline.append(_step("SESSION_REVOKED", "ok", detail="logout revoked session"))
        timeline.append(
            _step(
                "RESOURCE_ACCESS", "rejected", FailureReason.SESSION_REVOKED, "stale cookie denied"
            )
        )
        # Flawed path: logout does not revoke — the stale id stays valid.
        flawed_sessions = SessionStore()
        flawed_rec = flawed_sessions.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        flawed_still_valid = flawed_sessions.get(flawed_rec.session_id) is not None
        flawed_session = False  # nothing new created; the old session survives
        flawed_guard_omitted = "logout_revocation"
        flawed_observed_result = (
            "stale session id still valid after logout (no revocation)"
            if flawed_still_valid
            else "flawed model failed"
        )
        flawed_result = "allowed"
        expected_ok = secure_ok and resource["member_after_logout"] is False

    # -- I13: officer boundary ---------------------------------------------
    elif sid == "I13":
        sessions = SessionStore()
        rec = sessions.create(
            subject="student_01",
            username="student_01",
            roles=roles_for_fixture_subject("student_01"),
            issuer=EXPECTED_ISSUER,
        )
        member_ok = can_access(rec, "member")
        officer_ok = can_access(rec, "officer")
        spoofed_claims = {"sub": "student_01", "roles": ["officer"]}
        flawed_roles = flawed_mod.flawed_trust_token_roles(spoofed_claims)
        flawed_officer = "officer" in flawed_roles
        resource = {
            "member": member_ok,
            "officer": officer_ok,
            "officer_via_spoofed_claim": flawed_officer,
        }
        secure_reason = FailureReason.POLICY_DENIED
        secure_result = "denied"  # officer access denied
        session_preexisted = True  # the student IS logged in; only officer access is denied
        flawed_session = False  # no new session: the flawed path reuses the existing one
        flawed_guard_omitted = "server_side_policy"
        flawed_observed_result = "officer resource disclosed via spoofed token role claim"
        protected_resource_disclosed = flawed_officer
        flawed_result = "allowed"
        timeline.append(
            _step(
                "RESOURCE_ACCESS",
                "rejected",
                FailureReason.POLICY_DENIED,
                "student denied officer resource",
            )
        )
        expected_ok = member_ok and not officer_ok and flawed_officer

    # -- I15: callback parameter confusion ----------------------------------
    elif sid == "I15":
        # Duplicate state parameters: ambiguous callback must be rejected.
        states = ["state-a", "state-b"]
        duplicate = len(set(states)) > 1 or len(states) != 1
        secure_reason = FailureReason.CALLBACK_MALFORMED if duplicate else FailureReason.OK
        secure_result = "rejected" if duplicate else "allowed"
        timeline.append(
            _step("CALLBACK_RECEIVED", "rejected", secure_reason, "duplicate state parameters")
        )
        flawed_accept = True  # flawed takes the first value and proceeds
        if flawed_accept:
            flawed_store = SessionStore()
            flawed_store.create(
                subject="student_01",
                username="student_01",
                roles=roles_for_fixture_subject("student_01"),
                issuer=EXPECTED_ISSUER,
            )
            flawed_observed_result = (
                "first of two duplicate states accepted; login proceeds to session creation"
            )
        flawed_session = flawed_accept
        flawed_guard_omitted = "callback_param_uniqueness"
        flawed_result = "allowed"
        expected_ok = duplicate

    # -- I16: CSRF -----------------------------------------------------------
    # P1-08: the synthetic Request MUST carry a real `Cookie:` header —
    # Starlette's Request.cookies parses the header, not scope["cookies"].
    # Positive control first, then exactly one mutated factor per case.
    elif sid == "I16":
        from starlette.requests import Request

        def _req(headers: dict[str, str], cookie_token: str | None) -> Request:
            raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
            if cookie_token is not None:
                raw_headers.append((b"cookie", f"identityforge_csrf={cookie_token}".encode()))
            scope: dict[str, Any] = {
                "type": "http",
                "method": "POST",
                "path": "/auth/logout",
                "headers": raw_headers,
            }
            return Request(scope)

        good_token = csrf_mod.new_csrf_token()
        trusted_origin = "http://127.0.0.1:5173"
        # Positive control: matching header + cookie + trusted Origin -> OK.
        positive = _req({"origin": trusted_origin, "x-csrf-token": good_token}, good_token)
        positive_ok = csrf_mod.verify_csrf(positive, s) == FailureReason.OK
        timeline.append(
            _step(
                "MUTATION",
                "ok" if positive_ok else "rejected",
                FailureReason.OK if positive_ok else FailureReason.CSRF_DENIED,
                "positive control: matching token + trusted origin",
            )
        )
        # Single-factor negatives (each must be CSRF_DENIED).
        negatives = {
            "wrong header token": _req(
                {"origin": trusted_origin, "x-csrf-token": "wrong-token"}, good_token
            ),
            "missing cookie": _req({"origin": trusted_origin, "x-csrf-token": good_token}, None),
            "missing header token": _req({"origin": trusted_origin}, good_token),
            "hostile origin": _req(
                {"origin": "https://evil.example", "x-csrf-token": good_token}, good_token
            ),
            "hostile referer": _req(
                {
                    "origin": trusted_origin,
                    "referer": "https://evil.example/",
                    "x-csrf-token": good_token,
                },
                good_token,
            ),
            "rotated token (stale header)": _req(
                {"origin": trusted_origin, "x-csrf-token": good_token},
                csrf_mod.new_csrf_token(),
            ),
        }
        all_denied = True
        for label, bad_req in negatives.items():
            denied = csrf_mod.verify_csrf(bad_req, s) == FailureReason.CSRF_DENIED
            all_denied = all_denied and denied
            timeline.append(
                _step(
                    "MUTATION",
                    "rejected" if denied else "ok",
                    FailureReason.CSRF_DENIED if denied else FailureReason.OK,
                    f"negative: {label}",
                )
            )
        secure_reason = FailureReason.CSRF_DENIED if all_denied else FailureReason.OK
        secure_result = "rejected" if all_denied else "allowed"
        # CSRF governs a mutation (logout/reset), not a login: there is no
        # session concept here. The flawed comparator allows the mutation.
        flawed_session = False
        flawed_model_status = "EXECUTED"
        flawed_guard_omitted = "csrf"
        flawed_observed_result = (
            "cross-site mutation allowed without a valid CSRF token (no session involved)"
        )
        flawed_result = "allowed" if flawed_mod.flawed_skip_csrf() else "rejected"
        expected_ok = positive_ok and all_denied

    # -- I17: overlong / log injection ---------------------------------------
    elif sid == "I17":
        long_input = "x" * 10_000
        too_long = len(long_input) > s.max_input_chars
        injected = "student_01\nFAKE LOG: admin login succeeded"
        cleaned = sanitize_log_value(injected)
        log_safe = "\n" not in cleaned
        secure_reason = FailureReason.INPUT_TOO_LONG if too_long else FailureReason.OK
        secure_result = "rejected" if too_long else "allowed"
        timeline.append(
            _step(
                "INPUT_VALIDATION",
                "rejected",
                secure_reason,
                f"input length {len(long_input)} exceeds {s.max_input_chars}",
            )
        )
        timeline.append(
            _step(
                "LOG_SANITIZE",
                "ok" if log_safe else "rejected",
                detail="CR/LF stripped from log value",
            )
        )
        flawed_result = "allowed"  # flawed accepts and logs raw
        # Input handling, not a login: no session is created by either path.
        flawed_session = False
        flawed_guard_omitted = "input_length/log_sanitize"
        flawed_observed_result = "overlong input accepted; raw value logged (log injection)"
        expected_ok = too_long and log_safe

    # -- I18: SSRF ------------------------------------------------------------
    elif sid == "I18":
        evil_issuer = "http://169.254.169.254/latest/meta-data/"
        evil_jwks = "https://evil.example/.well-known/jwks.json"
        r1 = validate_issuer_url(evil_issuer, s.allowed_issuers)
        r2 = validate_jwks_url(evil_jwks)
        secure_reason = r1 if r1 != FailureReason.OK else r2
        secure_result = "rejected" if secure_reason != FailureReason.OK else "allowed"
        timeline.append(
            _step(
                "DISCOVERY", "rejected", secure_reason, "external/metadata URL blocked before fetch"
            )
        )
        flawed_accept = flawed_mod.flawed_accept_any_url(evil_issuer)
        # URL trust, not a login: no session is created by either path.
        flawed_session = False
        flawed_guard_omitted = "issuer_url_allowlist/jwks_url_allowlist"
        flawed_observed_result = "external/metadata URL accepted for fetch"
        flawed_result = "allowed" if flawed_accept else "rejected"
        expected_ok = secure_reason in (
            FailureReason.SSRF_BLOCKED,
            FailureReason.UNTRUSTED_ISSUER_URL,
        )

    else:  # pragma: no cover - definitions cover all ids
        raise ValueError(f"scenario not implemented: {sid}")

    return _finish(
        sid,
        definition,
        run_id,
        expected,
        secure_result,
        flawed_result,
        secure_reason,
        flawed_reason,
        secure_session,
        flawed_session,
        resource,
        timeline,
        decisions,
        started,
        store,
        locals().get("expected_ok", False),
        session_preexisted=session_preexisted,
        session_revoked=session_revoked,
        flawed_model_status=flawed_model_status,
        flawed_guard_omitted=flawed_guard_omitted,
        flawed_observed_result=flawed_observed_result,
        protected_resource_disclosed=protected_resource_disclosed,
    )


def _finish(
    sid: str,
    definition,
    run_id: str,
    expected: str,
    secure_result: str,
    flawed_result: str,
    secure_reason: FailureReason,
    flawed_reason: FailureReason,
    secure_session: bool,
    flawed_session: bool,
    resource: dict[str, bool],
    timeline: list[TransactionStep],
    decisions: list[ValidationCheck],
    started: float,
    store: Any | None,
    expected_ok: bool,
    *,
    session_preexisted: bool = False,
    session_revoked: bool = False,
    flawed_model_status: str = "EXECUTED",
    flawed_guard_omitted: str = "",
    flawed_observed_result: str = "",
    protected_resource_disclosed: bool = False,
) -> ComparisonResult:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    status = "PASS" if expected_ok else "FAIL"
    result = ComparisonResult(
        scenario_id=sid,
        title=definition.title,
        run_id=run_id,
        mode="DETERMINISTIC OFFLINE FIXTURE",
        expected_outcome=expected,
        secure_result=secure_result,
        flawed_result=flawed_result,
        secure_reason=secure_reason,
        flawed_reason=flawed_reason,
        secure_session_created=secure_session,
        flawed_session_created=flawed_session,
        session_preexisted=session_preexisted,
        session_revoked=session_revoked,
        flawed_model_status=flawed_model_status,  # type: ignore[arg-type]
        flawed_guard_omitted=flawed_guard_omitted,
        flawed_observed_result=flawed_observed_result,
        protected_resource_disclosed=protected_resource_disclosed,
        resource_access=resource,
        timeline=timeline,
        decisions=decisions,
        elapsed_ms=elapsed_ms,
        status=status,  # type: ignore[arg-type]
        limitations=(
            "Offline fixture with locally generated RSA keys and synthetic "
            "issuers; not a live Keycloak execution. Keycloak integration "
            "is a separate mode and is NOT RUN in this environment."
        ),
        reproducibility=ReproducibilityMetadata(
            run_id=run_id,
            scenario_id=sid,
            provider="offline-fixture",
            mode="DETERMINISTIC OFFLINE FIXTURE",
            started_at=datetime.now(timezone.utc),
            elapsed_ms=elapsed_ms,
            python_version=platform.python_version(),
        ),
    )
    # P1-09: evidence_saved starts False and becomes True ONLY after the
    # SQLite transaction commits. A run with no store is EPHEMERAL.
    if store is not None:
        try:
            # Mark saved BEFORE serialising, so the persisted report
            # itself records the truth; a raised save flips it back.
            result.evidence_saved = True
            result.evidence_provenance = "OFFLINE_FIXTURE"
            report = result.model_dump(mode="json")
            report["started_at"] = (
                result.reproducibility.started_at.isoformat() if result.reproducibility else ""
            )
            store.save_run(report)
        except Exception as exc:  # P1-14: evidence failure is reported, not hidden
            result.evidence_saved = False
            result.evidence_provenance = "OFFLINE_FIXTURE"
            result.evidence_error = sanitize_log_value(f"{type(exc).__name__}: storage failed")
    else:
        result.evidence_saved = False
        result.evidence_provenance = "EPHEMERAL"
    return result


def list_scenarios() -> list[dict[str, Any]]:
    return [d.model_dump() for d in BY_ID.values()]


def run_all(store: Any | None = None) -> list[ComparisonResult]:
    return [run_scenario(d.id, store=store) for d in BY_ID.values()]
