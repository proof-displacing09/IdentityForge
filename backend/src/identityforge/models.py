"""Typed Pydantic models for IdentityForge.

Every cross-boundary object (transaction, validation decision, session,
scenario result, evidence) is a typed model so tests and the API cannot
silently drift. No model ever carries a raw token, code, verifier, secret
or password — those values are redacted before storage (see
security/redaction.py).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SYNTHETIC_LABEL = "SYNTHETIC LAB DATA — NOT REAL IDENTITY INFORMATION"


class LabRole(str, Enum):
    MEMBER = "member"
    OFFICER = "officer"
    UNAUTHENTICATED = "unauthenticated"


class TestIdentity(BaseModel):
    sub: str
    username: str
    display_name: str
    roles: list[LabRole] = Field(default_factory=list)
    email: str | None = None  # synthetic only, e.g. student_01@lab.example


class ClientRegistration(BaseModel):
    client_id: str
    redirect_uris: list[str]
    issuer: str
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])


class TransactionStatus(str, Enum):
    CREATED = "CREATED"
    AUTHORIZATION_STARTED = "AUTHORIZATION_STARTED"
    CALLBACK_RECEIVED = "CALLBACK_RECEIVED"
    CODE_REDEEMED = "CODE_REDEEMED"
    TOKEN_VERIFIED = "TOKEN_VERIFIED"
    SESSION_CREATED = "SESSION_CREATED"
    REJECTED = "REJECTED"


class TransactionStep(BaseModel):
    step: str
    outcome: Literal["ok", "rejected", "error", "skipped"]
    reason_code: str | None = None
    # Alias for frontend consumers: mirrors reason_code.
    reason: str | None = None
    detail: str = ""
    at: datetime | None = None

    @model_validator(mode="after")
    def _fill_reason(self) -> "TransactionStep":
        if self.reason is None:
            self.reason = self.reason_code
        return self


class Transaction(BaseModel):
    transaction_id: str
    state: str  # stored as a hash reference only in evidence; raw value in-memory
    nonce: str
    code_verifier: str
    code_challenge: str
    redirect_uri: str
    client_id: str
    issuer: str
    # SHA-256 of the browser-bound transaction cookie value; raw value is
    # never stored (P0-07). Empty for fixture transactions.
    binding_token_hash: str = ""
    # SHA-256 of the anonymous browser key (identityforge_browser
    # cookie) that started this login; empty for fixture transactions.
    # Used ONLY for per-browser quota accounting (P1-10, v4) — the raw
    # key is never stored, logged, or put in evidence.
    browser_key_hash: str = ""
    status: TransactionStatus = TransactionStatus.CREATED
    created_at: datetime
    expires_at: datetime
    consumed: bool = False
    steps: list[TransactionStep] = Field(default_factory=list)


class FailureReason(str, Enum):
    OK = "OK"
    WRONG_ISSUER = "WRONG_ISSUER"
    WRONG_AUDIENCE = "WRONG_AUDIENCE"
    BAD_SIGNATURE = "BAD_SIGNATURE"
    ALG_NOT_ALLOWED = "ALG_NOT_ALLOWED"
    EXPIRED = "EXPIRED"
    NOT_YET_VALID = "NOT_YET_VALID"
    NONCE_MISMATCH = "NONCE_MISMATCH"
    MISSING_CLAIM = "MISSING_CLAIM"
    MALFORMED_TOKEN = "MALFORMED_TOKEN"
    UNKNOWN_KEY = "UNKNOWN_KEY"
    STATE_MISMATCH = "STATE_MISMATCH"
    STATE_MISSING = "STATE_MISSING"
    STATE_REUSED = "STATE_REUSED"
    STATE_BINDING_MISMATCH = "STATE_BINDING_MISMATCH"
    UNKNOWN_SUBJECT = "UNKNOWN_SUBJECT"
    PKCE_MISMATCH = "PKCE_MISMATCH"
    CODE_REUSED = "CODE_REUSED"
    CODE_EXPIRED = "CODE_EXPIRED"
    REDIRECT_URI_MISMATCH = "REDIRECT_URI_MISMATCH"
    CALLBACK_MALFORMED = "CALLBACK_MALFORMED"
    POLICY_DENIED = "POLICY_DENIED"
    SESSION_REVOKED = "SESSION_REVOKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_FIXATION = "SESSION_FIXATION"
    CSRF_DENIED = "CSRF_DENIED"
    SSRF_BLOCKED = "SSRF_BLOCKED"
    UNTRUSTED_ISSUER_URL = "UNTRUSTED_ISSUER_URL"
    INPUT_TOO_LONG = "INPUT_TOO_LONG"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    JWKS_ERROR = "JWKS_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"


class ValidationCheck(BaseModel):
    name: str
    passed: bool
    reason_code: FailureReason = FailureReason.OK
    detail: str = ""


class ValidationDecision(BaseModel):
    valid: bool
    reason_code: FailureReason = FailureReason.OK
    checks: list[ValidationCheck] = Field(default_factory=list)
    subject: str | None = None
    issuer: str | None = None
    audience: str | None = None
    # Redacted claims only (sub/iss/aud/exp); never raw tokens.
    claims_summary: dict[str, Any] = Field(default_factory=dict)


class SessionRecord(BaseModel):
    session_id: str
    subject: str
    username: str
    roles: list[LabRole] = Field(default_factory=list)
    issuer: str
    created_at: datetime
    expires_at: datetime
    revoked: bool = False
    rotated_from: str | None = None
    # P0-05: correlation id of the real login that created this session,
    # so portal authorization decisions join the login's live timeline.
    login_correlation_id: str = ""


class LiveLoginEvent(BaseModel):
    """One redacted, BFF-observed step of a REAL Keycloak login (P0-05).

    Only what the backend actually observed: a stage, an outcome, a
    reason code, a safe correlation id and a hash/pseudonym of the
    synthetic subject. NEVER a raw token, code, state, PKCE verifier,
    client secret, password, cookie or authorization URL. The IdP's
    internal password authentication is NOT observed — stages the BFF
    cannot see are recorded as NOT OBSERVED, never SUCCESS by assumption.
    """

    correlation_id: str  # transaction_id, or a hash-derived id pre-lookup
    stage: Literal[
        "AUTH_STARTED",
        "CALLBACK_RECEIVED",
        "BINDING_VERIFIED",
        "TOKEN_ENDPOINT",
        "ID_TOKEN_VALIDATED",
        "SESSION_CREATED",
        "AUTHORIZATION_DECISION",
        "LOGOUT",
    ]
    outcome: Literal["ok", "rejected", "error"]
    reason_code: str = "OK"
    subject_hash: str = ""  # SHA-256 hex of the (synthetic) subject, or ""
    username: str = ""  # synthetic pseudonym only (student_01 / officer_01)
    detail: str = ""  # safe, redacted; never a URL carrying a code/state
    at: datetime | None = None


class Finding(BaseModel):
    scenario_id: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    title: str
    description: str
    remediation: str = ""


class ReproducibilityMetadata(BaseModel):
    run_id: str
    scenario_id: str
    fixture_revision: str = "1.0.0"
    provider: str = "offline-fixture"  # or "keycloak-local"
    mode: str = "DETERMINISTIC OFFLINE FIXTURE"
    started_at: datetime
    elapsed_ms: int = 0
    python_version: str = ""
    code_revision: str = "uncommitted-local"


class EvidenceArtifact(BaseModel):
    artifact_id: str
    run_id: str
    kind: str  # e.g. "run-report", "event-log"
    sha256: str
    canonical_json: str = ""


class ComparisonResult(BaseModel):
    scenario_id: str
    title: str
    run_id: str
    mode: str = "DETERMINISTIC OFFLINE FIXTURE"
    expected_outcome: str
    secure_result: str
    flawed_result: str
    secure_reason: FailureReason = FailureReason.OK
    flawed_reason: FailureReason = FailureReason.OK
    # Session semantics (P0-06): these fields describe what ACTUALLY
    # happened in the test, never a convenient boolean.
    # - secure_session_created: SessionStore.create/rotate EXECUTED on the
    #   secure path of this run (I1 login, I11 rotation).
    # - session_preexisted: a legitimate session already existed before
    #   the tested action (I10 first redemption, I13 student login,
    #   I12 login before logout). A denied action leaves it valid.
    # - session_revoked: a session was revoked by the tested action (I12).
    secure_session_created: bool = False
    flawed_session_created: bool = False
    session_preexisted: bool = False
    session_revoked: bool = False
    # Flawed-comparator semantics (P0-06): the flawed side is a
    # one-check-omission fixture. flawed_model_status is NOT_MODELED
    # when the scenario has no meaningful session/flawed path; the
    # flawed decision itself is still recorded in flawed_result.
    flawed_model_status: Literal["EXECUTED", "NOT_MODELED"] = "EXECUTED"
    flawed_guard_omitted: str = ""
    flawed_observed_result: str = ""
    # True only when the flawed path discloses a protected resource to
    # an actor who must not have it (I13 spoofed officer role).
    protected_resource_disclosed: bool = False
    resource_access: dict[str, bool] = Field(default_factory=dict)
    timeline: list[TransactionStep] = Field(default_factory=list)
    decisions: list[ValidationCheck] = Field(default_factory=list)
    elapsed_ms: int = 0
    status: Literal["PASS", "FAIL", "ERROR", "SKIPPED", "INCONCLUSIVE"] = "PASS"
    limitations: str = ""
    reproducibility: ReproducibilityMetadata | None = None
    # P1-09: evidence state. Defaults to NOT saved; set to SAVED only
    # AFTER the SQLite transaction commits. A run with no store is
    # EPHEMERAL — it must never claim persisted evidence.
    evidence_saved: bool = False
    evidence_error: str = ""
    evidence_provenance: str = "OFFLINE_FIXTURE"  # OFFLINE_FIXTURE | LIVE_KEYCLOAK | EPHEMERAL

    # Frontend-facing aliases (same facts, names the UI contract uses).
    timestamp: datetime | None = None
    observed_secure: str = ""
    observed_flawed: str = ""
    validation_reason: str = ""
    resource_access_outcome: str = ""

    @model_validator(mode="after")
    def _fill_aliases(self) -> "ComparisonResult":
        if not self.observed_secure:
            self.observed_secure = self.secure_result
        if not self.observed_flawed:
            self.observed_flawed = self.flawed_result
        if not self.validation_reason:
            self.validation_reason = self.secure_reason.value
        if not self.resource_access_outcome:
            parts = [f"{k}={'allowed' if v else 'denied'}" for k, v in self.resource_access.items()]
            self.resource_access_outcome = (
                "; ".join(parts)
                if parts
                else ("session_created" if self.secure_session_created else "no_session")
            )
        if self.timestamp is None and self.reproducibility is not None:
            self.timestamp = self.reproducibility.started_at
        return self


class ScenarioDefinition(BaseModel):
    id: str
    title: str
    explanation: str
    attack_surface: str
    attacker_input: str
    expected_secure: str
    flawed_description: str
    decision_step: str
    remediation: str = ""
