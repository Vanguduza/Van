from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from van_gateway.action.models import ExecutionStatus, VerificationObservation
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService
from van_gateway.audit.service import AuditService
from van_gateway.authority.descriptor import Gate, gate_for
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.auth.throttle import AuthThrottle, Throttled
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityRecord, CommandAuthorityService
from van_gateway.command import context_requirements
from van_gateway.command.ingress_trust import derive_effective_trust
from van_gateway.command.local_executors import LOCAL_EXECUTORS, LocalExecutionContext, LocalExecutionError
from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.command.nonce import CommandNonceService, NonceReplay
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.context.authoring import OwnerFactAuthor
from van_gateway.context.models import ReadinessState
from van_gateway.context.service import OwnerContextService
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.hermes.bridge import HermesBridge, HermesBridgeError
from van_gateway.idempotency.service import IdempotencyConflict, IdempotencyInFlight, IdempotencyService
from van_gateway.mission.models import MissionState
from van_gateway.mission.service import MissionError
from van_gateway.observability import instruments
from van_gateway.observability.logging import log_event
from van_gateway.models import (
    ActionClass,
    CommandRequest,
    CommandResult,
    ContentTrust,
    DegradedCode,
    OriginChannel,
    PrincipalType,
)
from van_gateway.projects.router import ProjectRouter
from van_gateway.reminders.service import ReminderService
from van_gateway.voice.speaker import (
    SpeakerDisposition,
    classify_speaker_evidence,
    speaker_disposition,
)

LOGGER = logging.getLogger("van.command")


#: A4 approval failures that only a forger produces. An expired challenge, a missing proof
#: or a revoked device are legitimate states the owner's own client reaches, so they must
#: never contribute to the brute-force lockout (P1-SEC-007).
FORGERY_SHAPED_APPROVAL_ERRORS = frozenset(
    {
        "approval_signature_invalid",
        "approval_challenge_binding_mismatch",
        "approval_intent_mismatch",
        "approval_challenge_unknown_or_consumed",
        "approval_challenge_corrupt",
        "approval_public_key_wrong_type",
    }
)


INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "send secrets",
    "disable audit",
    "disable approvals",
)


class CommandOrchestrator:
    def __init__(
        self,
        *,
        auth: AuthService,
        idempotency: IdempotencyService,
        hermes: HermesBridge,
        projects: ProjectRouter,
        audit: AuditService,
        degraded: DegradedRegistry,
        context: OwnerContextService,
        authority: CommandAuthorityService,
        resolver: TypedCommandResolver,
        owner_intent_max_age_seconds: int,
        throttle: AuthThrottle | None = None,
        missions: CommandMissionLink | None = None,
        actions: ActionRuntime | None = None,
        owner_fact_author: OwnerFactAuthor | None = None,
        reminders: ReminderService | None = None,
        trading: Any | None = None,
        jev: Any | None = None,
        learning: Any | None = None,
    ) -> None:
        self.auth = auth
        self.idempotency = idempotency
        self.hermes = hermes
        self.projects = projects
        self.audit = audit
        self.degraded = degraded
        self.context = context
        self.authority = authority
        self.resolver = resolver
        self.approvals = OwnerApprovalService(auth.store)
        self.nonces = CommandNonceService(auth.store)
        # P1-SEC-007. Defaulted rather than required so a directly constructed
        # orchestrator in a test still has a real counter, never a None to guard on.
        self.throttle = throttle or AuthThrottle()
        # P0-EXEC-001. Optional so an orchestrator constructed directly in a test keeps
        # working, but create_app always supplies one: without it an accepted command
        # leaves no durable record of what the owner asked for.
        self.missions = missions
        # GAP-F-001, GAP-F-002, GAP-F-005 — the services a gateway-executed typed action
        # (command/local_executors.py) needs. All optional and all None by default so an
        # orchestrator built directly in a test keeps working; a resolution naming a
        # LOCAL_EXECUTORS action falls back to the Hermes dispatch path when `actions` is
        # not wired, rather than executing with services it does not have.
        self.actions = actions
        self.owner_fact_author = owner_fact_author
        self.reminders = reminders
        self.trading = trading
        self.jev = jev
        # GAP-F-008 (strategies_for read-back) — what VAN has already learned that this
        # mission's authority permits, attached to `canonical_context` as
        # `permitted_strategies`. None by default; without it a command simply carries no
        # strategy hints, which is the same "recorded, never read" state the gap named.
        self.learning = learning
        self.owner_intent_max_age_seconds = owner_intent_max_age_seconds

    @staticmethod
    def _legacy_provenance_is_default(req: CommandRequest) -> bool:
        return (
            req.turn_id is None
            and req.origin_channel == OriginChannel.UI
            and req.principal_type == PrincipalType.OWNER_DEVICE
            and req.requested_by == "owner_device"
            and req.expires_at_unix is None
            and req.nonce is None
            and req.context_capsule_revision is None
            and req.context_capsule_hash is None
            and req.speech_evidence_ref is None
            and req.speaker_evidence_milli is None
            and not req.no_stale_replay
        )

    async def handle(self, req: CommandRequest) -> CommandResult:
        """Handle the command, then log its outcome exactly once.

        The logging is a wrapper rather than a call at each `return` because
        `_handle` returns in twenty-one places, most of them refusals. A per-site
        call would be twenty-one chances to miss one, and the refusals are the
        lines an operator most needs — "VAN did nothing and said nothing" is the
        report this gate exists to make impossible.
        """
        result = await self._handle(req)
        self._log_outcome(req, result)
        return result

    async def _handle(self, req: CommandRequest) -> CommandResult:
        payload = req.model_dump()
        try:
            prior = await self.idempotency.begin(req.idempotency_key, payload)
            if prior is not None:
                return CommandResult(**prior)
        except IdempotencyConflict:
            result = CommandResult(
                status="conflict",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Idempotency key reused with different request",
            )
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result
        except IdempotencyInFlight:
            return CommandResult(
                status="in_flight",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Command already in flight",
            )

        try:
            await self.auth.require_device(req.device_id)
            if req.signature_version == 1:
                if not self._legacy_provenance_is_default(req):
                    raise AuthError(
                        "legacy_signature_cannot_bind_provenance",
                        "Signature v1 cannot carry Rev 3.1 provenance/replay fields",
                    )
                canonical = AuthService.canonical_command(
                    req.command_id,
                    req.idempotency_key,
                    req.device_id,
                    req.issued_at_unix,
                    req.text,
                    req.action_class.value,
                    req.project_id,
                )
            elif req.signature_version == 2:
                if req.speaker_evidence_milli is not None:
                    raise AuthError(
                        "unsigned_speaker_evidence",
                        "Signature v2 cannot bind speaker evidence; use signature v3",
                    )
                if req.principal_type != PrincipalType.OWNER_DEVICE:
                    raise AuthError("invalid_owner_device_principal", "Owner-device ingress must use OWNER_DEVICE principal")
                expected_requester = f"device:{req.device_id}"
                if req.requested_by != expected_requester:
                    raise AuthError("requested_by_mismatch", "requested_by must match authenticated owner device")
                canonical = AuthService.canonical_command_v2(
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    device_id=req.device_id,
                    issued_at_unix=req.issued_at_unix,
                    text=req.text,
                    action_class=req.action_class.value,
                    project_id=req.project_id,
                    turn_id=req.turn_id,
                    origin_channel=req.origin_channel.value,
                    principal_type=req.principal_type.value,
                    requested_by=req.requested_by,
                    expires_at_unix=req.expires_at_unix,
                    nonce=req.nonce,
                    context_capsule_revision=req.context_capsule_revision,
                    context_capsule_hash=req.context_capsule_hash,
                    speech_evidence_ref=req.speech_evidence_ref,
                    no_stale_replay=req.no_stale_replay,
                    context_trust=req.context_trust.value,
                )
            elif req.signature_version == 3:
                if req.principal_type != PrincipalType.OWNER_DEVICE:
                    raise AuthError("invalid_owner_device_principal", "Owner-device ingress must use OWNER_DEVICE principal")
                expected_requester = f"device:{req.device_id}"
                if req.requested_by != expected_requester:
                    raise AuthError("requested_by_mismatch", "requested_by must match authenticated owner device")
                canonical = AuthService.canonical_command_v3(
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    device_id=req.device_id,
                    issued_at_unix=req.issued_at_unix,
                    text=req.text,
                    action_class=req.action_class.value,
                    project_id=req.project_id,
                    turn_id=req.turn_id,
                    origin_channel=req.origin_channel.value,
                    principal_type=req.principal_type.value,
                    requested_by=req.requested_by,
                    expires_at_unix=req.expires_at_unix,
                    nonce=req.nonce,
                    context_capsule_revision=req.context_capsule_revision,
                    context_capsule_hash=req.context_capsule_hash,
                    speech_evidence_ref=req.speech_evidence_ref,
                    speaker_evidence_milli=req.speaker_evidence_milli,
                    no_stale_replay=req.no_stale_replay,
                    context_trust=req.context_trust.value,
                )
            else:
                raise AuthError("unsupported_signature_version", "Unsupported command signature version")
            self.auth.verify_signature(req.device_id, canonical, req.signature)
        except AuthError as exc:
            # P1-SEC-007, soft posture: the signature has already been judged invalid, so
            # counting it cannot keep a correctly signed owner command out. Past the policy
            # the command is refused before resolution, execution or Hermes dispatch.
            message, reason = exc.message, exc.code
            try:
                self.throttle.fail("command_signature", req.device_id)
            except Throttled as locked:
                message = (
                    "Too many invalid signatures from this device; "
                    f"retry in {locked.retry_after_seconds}s"
                )
                reason = f"signature_throttled:{locked.retry_after_seconds}"
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message=message,
            )
            await self.audit.record(result="denied", command_id=req.command_id, device_id=req.device_id, failure_reason=reason)
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result
        self.throttle.record_success("command_signature", req.device_id)

        if req.speaker_evidence_milli is not None and req.origin_channel != OriginChannel.VOICE:
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Speaker evidence is valid only for a live voice-origin command",
            )
            await self.audit.record(
                result="denied",
                command_id=req.command_id,
                device_id=req.device_id,
                failure_reason="speaker_evidence_non_voice_origin",
            )
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result


        # The nonce is covered by the v2/v3 signature and, until now, was never stored — so a
        # captured command could be replayed inside its validity window with a fresh
        # idempotency key (finding P1-SEC-005). Consume it after the signature verifies and
        # before anything observable happens.
        if req.nonce:
            try:
                await self.nonces.consume(
                    device_id=req.device_id,
                    nonce=req.nonce,
                    command_id=req.command_id,
                )
            except NonceReplay as replay:
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="Command nonce already used; replay refused",
                )
                await self.audit.record(
                    result="denied",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    failure_reason=f"nonce_replay:{replay.original_command_id}",
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

        resolution = self.resolver.resolve(req.text)
        effective_action_class = self.resolver.stronger_class(req.action_class, resolution.canonical_action_class)
        effective_no_stale_replay = req.no_stale_replay or resolution.no_stale_replay
        speaker_evidence = (
            classify_speaker_evidence(req.speaker_evidence_milli)
            if req.origin_channel == OriginChannel.VOICE
            else None
        )
        now = int(time.time())

        if req.expires_at_unix is not None and now >= req.expires_at_unix:
            result = CommandResult(
                status="expired",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Owner intent expiry reached; refusing replay",
            )
            await self.audit.record(result="expired", command_id=req.command_id, device_id=req.device_id, failure_reason="explicit_expiry")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        command_age = max(0, now - req.issued_at_unix)
        if resolution.max_age_seconds is not None and command_age > resolution.max_age_seconds:
            result = CommandResult(
                status="expired",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Typed action intent expired; refusing stale execution",
            )
            await self.audit.record(result="expired", command_id=req.command_id, device_id=req.device_id, failure_reason="typed_action_expired")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result
        if command_age > self.owner_intent_max_age_seconds:
            result = CommandResult(
                status="expired",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Owner intent expired; refusing stale offline replay",
            )
            await self.audit.record(result="expired", command_id=req.command_id, device_id=req.device_id, failure_reason="stale_intent")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        # P1-COH-003 — the gate comes from the descriptor rather than from a second copy
        # of the rule here. `gate_for`'s docstring already said "the gate the orchestrator
        # applies, expressed once", and it was expressed twice: here as `== A5` / `== A4`,
        # and there as a function nothing called. They agreed, because both derive from the
        # action class — but nothing made them agree, and the authority map asserted that
        # they did.
        required_gate = gate_for(effective_action_class)

        if required_gate is Gate.FORBIDDEN:
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="A5 prohibited action",
            )
            await self.audit.record(result="denied", command_id=req.command_id, device_id=req.device_id, failure_reason="A5")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        if speaker_evidence is not None:
            voice_disposition = speaker_disposition(effective_action_class, speaker_evidence)
            if voice_disposition is SpeakerDisposition.REFUSE:
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message=(
                        "This consequential voice command was refused because the local "
                        "speaker evidence did not match the enrolled owner profile"
                    ),
                    resolved_action_id=resolution.action_id,
                    effective_action_class=effective_action_class,
                )
                await self.audit.record(
                    result="denied",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    approval="not_applicable",
                    failure_reason="voice_speaker_mismatch",
                    before={"speaker_evidence": speaker_evidence.value},
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result
            if voice_disposition is SpeakerDisposition.REQUIRE_OWNER_APPROVAL:
                required_gate = Gate.OWNER_APPROVAL

        owner_approved = False
        if required_gate is Gate.OWNER_APPROVAL:
            if resolution.mode != ResolutionMode.EXACT_ACTION or not resolution.action_id:
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="Owner approval requires an exact gateway-resolved action",
                    effective_action_class=effective_action_class,
                )
                await self.audit.record(
                    result="denied",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    approval="not_applicable",
                    failure_reason="a4_requires_exact_typed_action",
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

            if req.approval_proof is None:
                challenge = await self.approvals.issue(
                    device_id=req.device_id,
                    source_command_id=req.command_id,
                    turn_id=req.turn_id,
                    action_id=resolution.action_id,
                    text=req.text,
                    project_id=req.project_id,
                )
                result = CommandResult(
                    status="approval_required",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="This action requires biometric owner approval bound to the paired device key",
                    requires_approval=True,
                    approval_challenge_id=challenge.challenge_id,
                    approval_challenge=challenge.canonical,
                    approval_expires_at_unix=challenge.expires_at_unix,
                    resolved_action_id=resolution.action_id,
                    effective_action_class=effective_action_class,
                    no_stale_replay=effective_no_stale_replay,
                    max_age_seconds=resolution.max_age_seconds,
                )
                await self.audit.record(
                    result="approval_required",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    approval="biometric_challenge_issued",
                    failure_reason="a4_owner_proof_missing",
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

            if req.approval_proof.algorithm != OwnerApprovalService.ALGORITHM:
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="Unsupported owner approval proof algorithm",
                    resolved_action_id=resolution.action_id,
                    effective_action_class=effective_action_class,
                )
                await self.audit.record(
                    result="denied",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    approval="invalid",
                    failure_reason="approval_algorithm_unsupported",
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

            try:
                await self.approvals.verify_and_consume(
                    challenge_id=req.approval_proof.challenge_id,
                    source_command_id=req.approval_proof.source_command_id,
                    signature_b64=req.approval_proof.signature_b64,
                    device_id=req.device_id,
                    turn_id=req.turn_id,
                    action_id=resolution.action_id,
                    text=req.text,
                    project_id=req.project_id,
                )
            except OwnerApprovalError as exc:
                message = "A4 owner approval proof is invalid, expired, or already consumed"
                reason = str(exc)
                # P1-SEC-007. An expired challenge or a missing proof is the owner being
                # slow or a client being wrong, not somebody guessing; only the outcomes
                # that a forger would produce count toward the lockout.
                if reason in FORGERY_SHAPED_APPROVAL_ERRORS:
                    try:
                        self.throttle.fail("approval_challenge", req.device_id)
                    except Throttled as locked:
                        message = (
                            "Too many invalid approval proofs from this device; "
                            f"retry in {locked.retry_after_seconds}s"
                        )
                        reason = f"approval_throttled:{reason}"
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message=message,
                    resolved_action_id=resolution.action_id,
                    effective_action_class=effective_action_class,
                )
                await self.audit.record(
                    result="denied",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    approval="invalid",
                    failure_reason=reason,
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result
            self.throttle.record_success("approval_challenge", req.device_id)
            owner_approved = True

        # A4 challenge requests do not execute, so NO_STALE_REPLAY is enforced only
        # after biometric proof exists and execution may proceed.
        if effective_no_stale_replay:
            max_window = min(60, resolution.max_age_seconds or 60)
            if req.expires_at_unix is None or req.expires_at_unix - req.issued_at_unix > max_window:
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message=f"NO_STALE_REPLAY requires an explicit expiry within {max_window} seconds",
                    resolved_action_id=resolution.action_id,
                    effective_action_class=effective_action_class,
                    no_stale_replay=True,
                    max_age_seconds=resolution.max_age_seconds,
                )
                await self.audit.record(
                    result="denied",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    failure_reason="invalid_no_stale_replay_window",
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

        # Trust is derived here, never taken from the request. A device signature proves
        # which device sent the envelope, not who authored the text inside it. See
        # command/ingress_trust.py and audit finding P0-SEC-002.
        effective_trust, downgrade_reason = derive_effective_trust(
            origin_channel=req.origin_channel,
            declared_trust=req.context_trust,
            text=req.text,
        )
        if downgrade_reason is not None:
            await self.audit.record(
                result="trust_downgraded",
                command_id=req.command_id,
                device_id=req.device_id,
                failure_reason=downgrade_reason,
            )

        if effective_trust == ContentTrust.UNTRUSTED:
            # Untrusted content is data. It may never carry an action class that mutates,
            # and it may never smuggle an instruction override.
            lowered = req.text.lower()
            injection = any(marker in lowered for marker in INJECTION_MARKERS)
            mutating = req.action_class not in (ActionClass.A1,)
            if injection or mutating:
                reason = "injection" if injection else "untrusted_content_cannot_mutate"
                result = CommandResult(
                    status="rejected_untrusted",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message=(
                        "Untrusted content attempted instruction override; treated as data only "
                        "and rejected for mutation"
                        if injection
                        else
                        "Content from a third-party channel is data and cannot request a mutating "
                        "action; an explicit owner action is required to act on it"
                    ),
                )
                await self.audit.record(
                    result="rejected_untrusted",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    failure_reason=reason,
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

        # P0-EXEC-001. This is the first point at which the command is established as
        # genuine owner intent: authenticated, unexpired, not A5, biometrically approved if
        # A4, and not third-party content wearing the owner's authority. Everything before
        # here is a refusal, which the audit log records and which is not owner work. From
        # here on the owner asked for something, so there is a mission whatever happens
        # next — including the paths where nothing happens.
        mission = None
        if self.missions is not None:
            mission = await self.missions.open(
                req,
                effective_action_class=effective_action_class,
                owner_approved=owner_approved,
                # P1-VERIFY-003 — the resolution is what says whether VAN understood the
                # command exactly enough to state a checkable post-state. Passing it here
                # is what lets an owner command reach VERIFIED_SUCCESS at all.
                resolution=resolution,
            )
            mission = await self.missions.understood(
                mission,
                summary=(
                    f"{resolution.mode.value}:{resolution.action_id}"
                    if resolution.mode == ResolutionMode.EXACT_ACTION
                    else f"free-form:{effective_action_class.value}"
                ),
            )

        before: dict[str, Any] = {
            "command_resolution": resolution.model_dump(mode="json"),
            "signed_action_class": req.action_class.value,
            "effective_action_class": effective_action_class.value,
        }
        if speaker_evidence is not None:
            before["speaker_evidence"] = speaker_evidence.value
        live_state_refs: list[str] = []
        policy_refs = [
            "security-policy:A1-A5",
            f"action-class:signed:{req.action_class.value}",
            f"action-class:effective:{effective_action_class.value}",
            f"principal:{req.principal_type.value}",
            f"resolver:{resolution.resolver_version}",
        ]
        if resolution.rule_id:
            policy_refs.append(f"resolver-rule:{resolution.rule_id}")
        if speaker_evidence is not None:
            policy_refs.append(f"speaker-evidence:{speaker_evidence.value}")
        if owner_approved:
            policy_refs.append("owner-approval:ECDSA_P256_SHA256")

        if req.project_id:
            truth = await self.projects.load_truth(req.project_id)
            if not truth.get("ok") and effective_action_class in (ActionClass.A3, ActionClass.A4):
                code = truth.get("degraded", DegradedCode.STALE_PROJECT_TRUTH.value)
                self.degraded.set(DegradedCode(code), True)
                if mission is not None:
                    mission = await self.missions.blocked_by_policy(
                        mission, reason=f"project_truth_gate:{code}"
                    )
                result = CommandResult(
                    status="degraded",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="Project Truth missing or stale; refusing mutation",
                    degraded=[code],
                    mission_id=mission.mission_id if mission else None,
                )
                await self.audit.record(
                    result="degraded",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    project_id=req.project_id,
                    failure_reason="truth_gate",
                    before={**truth, **before},
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result
            if truth.get("ok"):
                truth_sha = str(truth.get("truth_sha") or "")
                repo_sha = str(truth.get("repo_sha") or "")
                before["truth_sha"] = truth_sha
                before["repo_sha"] = repo_sha or None
                before["project_truth"] = {
                    "project_id": req.project_id,
                    "truth_sha": truth_sha,
                    "repo_sha": repo_sha or None,
                }
                live_state_refs.append(f"project-truth:{req.project_id}:{truth_sha}")
                if repo_sha:
                    live_state_refs.append(f"repo-head:{req.project_id}:{repo_sha}")

        # P0-CTX-001 — this passed `[]`, so readiness was trivially CURRENT, fact_ids was
        # always empty, and the canonical context handed to Hermes carried no owner facts
        # at all. The kernel was real and was never asked a question.
        requirements = context_requirements.derive(
            text=req.text,
            project_id=req.project_id,
            action_id=resolution.action_id if resolution.mode == ResolutionMode.EXACT_ACTION else None,
        )
        try:
            context_snapshot = await self.context.compile_snapshot(
                req.command_id,
                requirements,
                live_state_refs=live_state_refs,
                policy_refs=policy_refs,
            )
        except Exception as exc:
            self.degraded.set(DegradedCode.OWNER_CONTEXT_UNAVAILABLE, True)
            if mission is not None:
                await self.missions.note_stall(
                    mission, reason=f"owner_context_unavailable:{exc.__class__.__name__}"
                )
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Canonical owner context could not be sealed; command not dispatched",
                degraded=[DegradedCode.OWNER_CONTEXT_UNAVAILABLE.value],
                mission_id=mission.mission_id if mission else None,
            )
            await self.audit.record(
                result="degraded",
                command_id=req.command_id,
                device_id=req.device_id,
                project_id=req.project_id,
                failure_reason=f"context_snapshot:{exc.__class__.__name__}",
                before=before,
            )
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        self.degraded.set(DegradedCode.OWNER_CONTEXT_UNAVAILABLE, False)

        # GAP-F-019 — every derived requirement is non-blocking (safety actions must never
        # be blocked by missing memory, and that stays true here), but a requirement VAN
        # could not resolve was previously only visible as a bare "subject.predicate" pair
        # buried in `missing_requirements`. This re-runs the same readiness computation
        # `compile_snapshot` already performed (a second, side-effect-free read) so each gap
        # can carry the owner-readable label `context_requirements.label_for` gives it.
        readiness = await self.context.readiness(
            req.command_id, requirements, now_ms=int(time.time() * 1000)
        )
        context_gaps = [
            {
                "subject": resolution_item.requirement.subject,
                "predicate": resolution_item.requirement.predicate,
                "scope": resolution_item.requirement.scope,
                "state": resolution_item.state.value,
                "label": context_requirements.label_for(resolution_item.requirement),
            }
            for resolution_item in readiness.requirements
            if resolution_item.state in (ReadinessState.MISSING, ReadinessState.STALE)
        ]

        # GAP-F-008 (strategies_for read-back) — what VAN has already learned that this
        # mission class is permitted, under this command's own authority ceiling. Bounded
        # to 5 and reduced to an id and a one-line summary: this is a hint attached to the
        # context, not a plan the gateway or Hermes is bound to follow.
        permitted_strategies = await self._permitted_strategies(resolution, effective_action_class)

        canonical_context = {
            "snapshot_id": context_snapshot.snapshot_id,
            "digest": context_snapshot.digest,
            "kernel_revision": context_snapshot.kernel_revision,
            "fact_ids": context_snapshot.fact_ids,
            "live_state_refs": context_snapshot.live_state_refs,
            "policy_refs": context_snapshot.policy_refs,
            # What was asked and what was found, so a reader can tell "VAN knew nothing"
            # from "VAN asked nothing" — which was indistinguishable before.
            "requirements_asked": len(requirements),
            "readiness": context_snapshot.readiness_state,
            "context_gaps": context_gaps,
            "permitted_strategies": permitted_strategies,
        }
        before["canonical_context"] = canonical_context

        # What will happen is now decided: a typed action with its parameter constraints,
        # or delegation to the agent runtime under the envelope about to be sealed.
        if mission is not None:
            mission = await self.missions.planned(
                mission,
                summary=(
                    f"typed-action:{resolution.action_id}"
                    if resolution.mode == ResolutionMode.EXACT_ACTION
                    else "delegate-to-agent-runtime"
                ),
            )

        authority_record = CommandAuthorityRecord(
            command_id=req.command_id,
            device_id=req.device_id,
            principal_type=req.principal_type,
            requested_by=req.requested_by,
            origin_channel=req.origin_channel,
            signed_action_class=req.action_class,
            effective_action_class=effective_action_class,
            typed_action_id=resolution.action_id if resolution.mode == ResolutionMode.EXACT_ACTION else None,
            typed_parameter_constraints=(resolution.parameters if resolution.mode == ResolutionMode.EXACT_ACTION else {}),
            snapshot_id=context_snapshot.snapshot_id,
            context_digest=context_snapshot.digest,
            issued_at_unix=req.issued_at_unix,
            expires_at_unix=req.expires_at_unix,
            no_stale_replay=effective_no_stale_replay,
            owner_approved=owner_approved,
            turn_id=req.turn_id,
            sealed_at_unix_ms=int(time.time() * 1000),
        )
        try:
            await self.authority.seal(authority_record)
        except CommandAuthorityError as exc:
            if mission is not None:
                await self.missions.note_stall(mission, reason=f"authority_seal_failed:{exc}")
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Signed command authority could not be sealed; command not dispatched",
                context_snapshot_id=context_snapshot.snapshot_id,
                mission_id=mission.mission_id if mission else None,
            )
            await self.audit.record(
                result="denied",
                command_id=req.command_id,
                device_id=req.device_id,
                project_id=req.project_id,
                failure_reason=str(exc),
                before=before,
            )
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        if mission is not None:
            mission = await self.missions.authorized(
                mission, summary=f"authority-sealed:{effective_action_class.value}"
            )

        # GAP-F-001, GAP-F-002, GAP-F-005 — the gateway already owns this state (owner
        # facts, reminders, the trading kill switch), so a resolution naming one of these
        # actions is executed here rather than handed to Hermes, which has no tool for any
        # of them. `self.actions` is None only when the orchestrator was built directly
        # without it (a test, or a deployment that has not wired it yet); in that case this
        # falls through to the Hermes dispatch below exactly as it always has.
        if (
            mission is not None
            and self.actions is not None
            and resolution.mode == ResolutionMode.EXACT_ACTION
            and resolution.action_id in LOCAL_EXECUTORS
        ):
            return await self._execute_local_action(
                req=req,
                resolution=resolution,
                mission=mission,
                context_snapshot=context_snapshot,
                effective_action_class=effective_action_class,
                effective_no_stale_replay=effective_no_stale_replay,
                owner_approved=owner_approved,
                before=before,
                context_gaps=context_gaps,
            )

        health = await self.hermes.health()
        if not health.get("ok"):
            self.degraded.set(DegradedCode.HERMES_OFFLINE, True)
            if mission is not None:
                await self.missions.note_stall(mission, reason="hermes_offline")
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Hermes offline; command not executed",
                degraded=[DegradedCode.HERMES_OFFLINE.value],
                context_snapshot_id=context_snapshot.snapshot_id,
                mission_id=mission.mission_id if mission else None,
            )
            await self.audit.record(result="degraded", command_id=req.command_id, device_id=req.device_id, failure_reason="hermes_offline", before=before)
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result
        self.degraded.set(DegradedCode.HERMES_OFFLINE, False)

        try:
            # P3-OBS-002 — Hermes dispatch latency is Gate 11's "Hermes callback
            # latency" for the synchronous half: how long the owner waits before VAN
            # can say the work has started at all.
            with instruments.timed() as dispatch_ms:
                run = await self.hermes.create_run(
                    req.text,
                    metadata={
                        "command_id": req.command_id,
                        "mission_id": mission.mission_id if mission else None,
                        "idempotency_key": req.idempotency_key,
                        "device_id": req.device_id,
                        "project_id": req.project_id,
                        "action_class": effective_action_class.value,
                        "signed_action_class": req.action_class.value,
                        "context_trust": effective_trust.value,
                        "declared_context_trust": req.context_trust.value,
                        "signature_version": req.signature_version,
                        "turn_id": req.turn_id,
                        "origin_channel": req.origin_channel.value,
                        "principal_type": req.principal_type.value,
                        "requested_by": req.requested_by,
                        "expires_at_unix": req.expires_at_unix,
                        "nonce": req.nonce,
                        "context_capsule_revision": req.context_capsule_revision,
                        "context_capsule_hash": req.context_capsule_hash,
                        "speech_evidence_ref": req.speech_evidence_ref,
                        "speaker_evidence": speaker_evidence.value if speaker_evidence else None,
                        "no_stale_replay": effective_no_stale_replay,
                        "client_context": req.client_context,
                        "client_context_authoritative": False,
                        "canonical_context": canonical_context,
                        "typed_resolution": resolution.model_dump(mode="json"),
                        "gateway_action_authority_required": True,
                        "owner_approved": owner_approved,
                    },
                )
            instruments.record_hermes_callback("accepted", dispatch_ms[0])
        except HermesBridgeError as exc:
            instruments.record_hermes_callback("failed", dispatch_ms[0])
            instruments.record_error("HermesBridgeError", exc.code)
            self.degraded.set(DegradedCode.HERMES_OFFLINE, True)
            if mission is not None:
                await self.missions.note_stall(mission, reason=f"hermes_dispatch_failed:{exc.code}")
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message=exc.message,
                degraded=[DegradedCode.HERMES_OFFLINE.value],
                context_snapshot_id=context_snapshot.snapshot_id,
                mission_id=mission.mission_id if mission else None,
            )
            await self.audit.record(result="degraded", command_id=req.command_id, device_id=req.device_id, failure_reason=exc.code, before=before)
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result

        evidence_id = await self.audit.record(
            result="accepted",
            command_id=req.command_id,
            device_id=req.device_id,
            project_id=req.project_id,
            capability=effective_action_class.value,
            approval="biometric_proof_verified" if owner_approved else "not_required",
            model_delegate="hermes:van",
            before=before,
            after={
                "hermes_run": run,
                "origin_channel": req.origin_channel.value,
                "principal_type": req.principal_type.value,
                "requested_by": req.requested_by,
                "turn_id": req.turn_id,
                "context_snapshot_id": context_snapshot.snapshot_id,
                "typed_action_id": authority_record.typed_action_id,
                "effective_action_class": effective_action_class.value,
                "owner_approved": owner_approved,
            },
            evidence_pointer=run.get("id"),
        )
        if mission is not None:
            mission = await self.missions.running(mission, hermes_run_id=run.get("id"))

        result = CommandResult(
            status="accepted",
            command_id=req.command_id,
            idempotency_key=req.idempotency_key,
            message="Accepted and routed to Hermes profile van with canonical owner context and sealed authority",
            mission_id=mission.mission_id if mission else None,
            hermes_run_id=run.get("id"),
            evidence_id=evidence_id,
            context_snapshot_id=context_snapshot.snapshot_id,
            resolved_action_id=authority_record.typed_action_id,
            effective_action_class=effective_action_class,
            no_stale_replay=effective_no_stale_replay,
            max_age_seconds=resolution.max_age_seconds,
            context_gaps=context_gaps,
        )
        await self.idempotency.complete(req.idempotency_key, result.model_dump())
        return result

    async def _execute_local_action(
        self,
        *,
        req: CommandRequest,
        resolution,
        mission,
        context_snapshot,
        effective_action_class: ActionClass,
        effective_no_stale_replay: bool,
        owner_approved: bool,
        before: dict[str, Any],
        context_gaps: list[dict[str, Any]],
    ) -> CommandResult:
        """GAP-F-001, GAP-F-002, GAP-F-005 — run a gateway-owned typed action in place of a
        Hermes dispatch.

        This reuses exactly the paths a Hermes-executed action already goes through —
        `ActionRuntime.begin`/`mark_executing`/`mark_submitted`/`verify` for the execution
        ledger (the same sequence `runtime_api.py`'s `/actions/*` routes drive on Hermes's
        behalf) — and `MissionService.transition` for RUNNING -> VERIFYING -> a verified
        terminal state, the same fallback `MissionService.apply_hermes_result` uses:
        attempt VERIFIED_SUCCESS, fall back to UNVERIFIABLE when the mission's success
        contract names no independent check for this action id. Neither ledger gets a
        parallel state machine.

        `status` on the returned `CommandResult` is "accepted" only when the local action
        actually succeeded. A failure never reaches "accepted" here — `_fail_local_action`
        reports "denied" for an owner/authority/parameter refusal or "degraded" for an
        infrastructure fault, exactly the wire vocabulary the rest of this method already
        uses for the same distinction. `local_execution` and the mission's own terminal
        state carry the detail either way.
        """
        parameters = dict(resolution.parameters)
        execution_id = f"exec_{uuid.uuid4().hex}"
        assert self.actions is not None
        definition = await self.actions.get_definition(resolution.action_id)
        if definition is None:
            # The registry and the resolver disagreed about which actions exist — a
            # programming error, not an owner-facing refusal.
            await self.missions.note_stall(mission, reason=f"unknown_local_action:{resolution.action_id}")
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="This action is not registered on the gateway; command not executed",
                degraded=["LOCAL_ACTION_UNREGISTERED"],
                mission_id=mission.mission_id,
                context_snapshot_id=context_snapshot.snapshot_id,
                resolved_action_id=resolution.action_id,
                effective_action_class=effective_action_class,
                context_gaps=context_gaps,
            )
            await self.audit.record(
                result="degraded", command_id=req.command_id, device_id=req.device_id,
                project_id=req.project_id, failure_reason="local_action_unregistered", before=before,
            )
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        try:
            authority, age = await self.authority.authorize_action(
                command_id=req.command_id, action=definition, principal_type=req.principal_type,
                requested_by=req.requested_by, snapshot_id=context_snapshot.snapshot_id,
                turn_id=req.turn_id, parameters=parameters,
            )
            execution = await self.actions.begin(
                execution_id=execution_id, command_id=req.command_id, turn_id=authority.turn_id,
                action_id=resolution.action_id, principal_type=authority.principal_type,
                requested_by=authority.requested_by, idempotency_key=req.idempotency_key,
                parameters=parameters, snapshot_id=authority.snapshot_id,
                owner_approved=authority.owner_approved, command_age_seconds=age,
            )
        except (CommandAuthorityError, ActionPolicyError) as exc:
            await self.missions.note_stall(mission, reason=f"local_action_authorize_failed:{exc}")
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="This action could not be authorised against the sealed command; command not executed",
                degraded=["LOCAL_ACTION_AUTHORITY_MISMATCH"],
                mission_id=mission.mission_id,
                context_snapshot_id=context_snapshot.snapshot_id,
                resolved_action_id=resolution.action_id,
                effective_action_class=effective_action_class,
                context_gaps=context_gaps,
            )
            await self.audit.record(
                result="degraded", command_id=req.command_id, device_id=req.device_id,
                project_id=req.project_id, failure_reason=str(exc), before=before,
            )
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        if execution.status != ExecutionStatus.AUTHORIZED:
            # DENIED (A5/disabled) or EXPIRED (no-stale-replay/max-age): both legal edges
            # out of AUTHORIZED. AUTHORIZATION_REQUIRED should not be reachable here, since
            # Gate.OWNER_APPROVAL already ran for any A4 action before this method is
            # called; if it somehow is, it is treated the same as DENIED rather than left
            # to raise.
            target_state = (
                MissionState.EXPIRED if execution.status == ExecutionStatus.EXPIRED
                else MissionState.BLOCKED_POLICY
            )
            result_status = "expired" if execution.status == ExecutionStatus.EXPIRED else "denied"
            mission_after = await self.missions.missions.transition(
                mission.mission_id, target=target_state, expected=mission.state,
                actor=PrincipalType.SYSTEM,
                summary=f"local action not authorized: {execution.error_code}",
                final_outcome=execution.error_code,
            )
            result = CommandResult(
                status=result_status,
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message=f"Action not executed: {execution.error_code}",
                mission_id=mission_after.mission_id,
                context_snapshot_id=context_snapshot.snapshot_id,
                resolved_action_id=resolution.action_id,
                effective_action_class=effective_action_class,
                execution_id=execution.execution_id,
                context_gaps=context_gaps,
            )
            await self.audit.record(
                result=result_status, command_id=req.command_id, device_id=req.device_id,
                project_id=req.project_id, failure_reason=execution.error_code, before=before,
            )
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        await self.actions.mark_executing(execution.execution_id)
        mission = await self.missions.running(mission, hermes_run_id=None)

        ctx = LocalExecutionContext(
            store=self.context.store,
            context=self.context,
            owner_fact_author=self.owner_fact_author,
            reminders=self.reminders,
            trading=self.trading,
            jev=self.jev,
            device_id=req.device_id,
            command_id=req.command_id,
            mission_id=mission.mission_id,
            parameters=parameters,
            client_context=req.client_context or {},
            now_ms=int(time.time() * 1000),
        )
        executor = LOCAL_EXECUTORS[resolution.action_id]()
        try:
            local_result = await executor.execute(ctx)
        except LocalExecutionError as exc:
            return await self._fail_local_action(
                req=req, resolution=resolution, mission=mission, execution_id=execution.execution_id,
                context_snapshot=context_snapshot, effective_action_class=effective_action_class,
                before=before, context_gaps=context_gaps, code=exc.code, message=exc.message,
                status=exc.status,
            )
        except Exception:  # pragma: no cover - defensive; never a false success
            LOGGER.exception(
                "local action executor raised unexpectedly",
                extra={"action_id": resolution.action_id, "command_id": req.command_id},
            )
            return await self._fail_local_action(
                req=req, resolution=resolution, mission=mission, execution_id=execution.execution_id,
                context_snapshot=context_snapshot, effective_action_class=effective_action_class,
                before=before, context_gaps=context_gaps, code="local_execution_error",
                message="This action could not be completed", status="degraded",
            )

        await self.actions.mark_submitted(
            execution.execution_id, correlation=local_result.observed_postcondition,
            evidence_pointer=local_result.evidence_ref,
        )
        receipt = await self.actions.verify(
            VerificationObservation(
                execution_id=execution.execution_id, success=True,
                # The executor already re-read the store independently of its own write
                # before reporting success (command/local_executors.py); this is that same
                # independently-observed postcondition, not the write call's own return
                # value.
                correlation=local_result.observed_postcondition,
                observed_postcondition=local_result.observed_postcondition,
                evidence_pointer=local_result.evidence_ref,
            )
        )

        mission = await self.missions.missions.transition(
            mission.mission_id, target=MissionState.VERIFYING, expected=MissionState.RUNNING,
            actor=PrincipalType.SYSTEM, summary="local execution complete; verifying independently",
        )
        if not mission.success_contract.is_checkable:
            mission = await self.missions.missions.transition(
                mission.mission_id, target=MissionState.UNVERIFIABLE, expected=MissionState.VERIFYING,
                actor=PrincipalType.SYSTEM,
                summary="executed locally; no mission-level independent postcondition is registered for this action",
                final_outcome=local_result.summary,
            )
        else:
            try:
                mission = await self.missions.missions.transition(
                    mission.mission_id, target=MissionState.VERIFIED_SUCCESS, expected=MissionState.VERIFYING,
                    actor=PrincipalType.SYSTEM, summary="Independent postcondition verification passed",
                    final_outcome=local_result.summary,
                )
            except MissionError as exc:
                if exc.code != "MISSION_VERIFICATION_INSUFFICIENT":
                    raise
                mission = await self.missions.missions.transition(
                    mission.mission_id, target=MissionState.UNVERIFIABLE, expected=MissionState.VERIFYING,
                    actor=PrincipalType.SYSTEM,
                    summary="executed locally, but independent mission-level verification was insufficient",
                    final_outcome=local_result.summary,
                )

        local_execution = {
            "action_id": resolution.action_id,
            "execution_id": execution.execution_id,
            "verification_state": receipt.status.value,
            "summary": local_result.summary,
            "evidence_ref": local_result.evidence_ref,
        }
        evidence_id = await self.audit.record(
            result="accepted", command_id=req.command_id, device_id=req.device_id,
            project_id=req.project_id, capability=effective_action_class.value,
            approval="biometric_proof_verified" if owner_approved else "not_required",
            model_delegate="gateway:local", before=before,
            after={
                "local_execution": local_execution,
                "mission_state": mission.state.value,
                "typed_action_id": resolution.action_id,
                "effective_action_class": effective_action_class.value,
                "owner_approved": owner_approved,
            },
            evidence_pointer=local_result.evidence_ref,
        )
        result = CommandResult(
            status="accepted",
            command_id=req.command_id,
            idempotency_key=req.idempotency_key,
            message=local_result.summary,
            mission_id=mission.mission_id,
            evidence_id=evidence_id,
            context_snapshot_id=context_snapshot.snapshot_id,
            resolved_action_id=resolution.action_id,
            effective_action_class=effective_action_class,
            no_stale_replay=effective_no_stale_replay,
            max_age_seconds=resolution.max_age_seconds,
            execution_id=execution.execution_id,
            local_execution=local_execution,
            context_gaps=context_gaps,
        )
        await self.idempotency.complete(req.idempotency_key, result.model_dump())
        return result

    async def _fail_local_action(
        self,
        *,
        req: CommandRequest,
        resolution,
        mission,
        execution_id: str,
        context_snapshot,
        effective_action_class: ActionClass,
        before: dict[str, Any],
        context_gaps: list[dict[str, Any]],
        code: str,
        message: str,
        status: str = "denied",
    ) -> CommandResult:
        """A local executor refused or could not complete. Never a false success: the
        execution ledger and the mission both end on a named failure, and `status` is
        never "accepted" — "denied" for an owner/authority/parameter refusal (a missing
        required field, a missing or invalid `owner_halt_authority_ref`), "degraded" for
        an infrastructure fault (a service not wired, a store that would not read back its
        own write). `local_execution.verification_state` and the mission's FAILED state
        carry the same detail for whichever reader wants it.
        """
        assert self.actions is not None
        await self.actions.fail_execution(
            execution_id, status=ExecutionStatus.EXECUTION_FAILED, error_code=code,
        )
        mission_after = await self.missions.missions.transition(
            mission.mission_id, target=MissionState.FAILED, expected=mission.state,
            actor=PrincipalType.SYSTEM, summary=message, final_outcome=code,
        )
        local_execution = {
            "action_id": resolution.action_id,
            "execution_id": execution_id,
            "verification_state": ExecutionStatus.EXECUTION_FAILED.value,
            "summary": message,
            "evidence_ref": None,
        }
        await self.audit.record(
            result=status, command_id=req.command_id, device_id=req.device_id,
            project_id=req.project_id, capability=resolution.action_id, before=before,
            after={"local_execution": local_execution, "mission_state": mission_after.state.value},
            failure_reason=code,
        )
        result = CommandResult(
            status=status,
            command_id=req.command_id,
            idempotency_key=req.idempotency_key,
            message=message,
            mission_id=mission_after.mission_id,
            context_snapshot_id=context_snapshot.snapshot_id,
            resolved_action_id=resolution.action_id,
            effective_action_class=effective_action_class,
            execution_id=execution_id,
            local_execution=local_execution,
            context_gaps=context_gaps,
        )
        await self.idempotency.complete(req.idempotency_key, result.model_dump())
        return result

    async def _permitted_strategies(
        self, resolution, effective_action_class: ActionClass,
    ) -> list[dict[str, Any]]:
        """GAP-F-008 (strategies_for read-back) — what VAN has already learned that this
        mission's authority actually permits, bounded to 5 entries of an id and a one-line
        summary. `mission_class` mirrors exactly what `CommandMissionLink.open` gives the
        mission itself, so this names the same strategies the mission's own outcome would
        one day be recorded under.
        """
        if self.learning is None:
            return []
        mission_class = resolution.intent_id or "GENERAL_OWNER_INTENT"
        try:
            rows = await self.learning.strategies_for(
                mission_class, envelope_max_action_class=effective_action_class,
            )
        except Exception:
            # A learning-store fault must never block or fail a command; strategies are a
            # hint layered on top of the context, not a dependency of it.
            return []
        strategies: list[dict[str, Any]] = []
        for row in rows[:5]:
            strategy_id = str(row.get("strategy_id") or "")
            try:
                sequence = json.loads(row.get("capability_sequence_json") or "[]")
            except (TypeError, ValueError):
                sequence = []
            sequence_text = (
                " -> ".join(str(step) for step in sequence) if sequence
                else "no capability sequence recorded"
            )
            summary = (
                f"{sequence_text} ({int(row.get('success_count') or 0)} succeeded, "
                f"{int(row.get('failure_count') or 0)} failed)"
            )
            strategies.append({"strategy_id": strategy_id, "summary": summary})
        return strategies

    def _log_outcome(self, req: CommandRequest, result: CommandResult) -> None:
        """One structured line per command outcome (P3-OBS-001).

        `result.correlation_id` rather than a locally derived one, so the line and
        the response the device received carry the same identifier by construction:
        an owner reading a correlation id off their screen finds this line.

        The command text is deliberately not logged. It is the owner's speech, it
        can contain anything they said, and a log is the one place it would end up
        in plaintext on disk outside the audit record that is meant to hold it.
        """
        log_event(
            LOGGER,
            logging.INFO if result.status == "accepted" else logging.WARNING,
            "command outcome",
            correlation_id=result.correlation_id,
            command_id=req.command_id,
            mission_id=result.mission_id,
            device_id=req.device_id,
            action_class=(result.effective_action_class or req.action_class).value,
            principal=req.principal_type.value,
            result=result.status,
            degraded_code=",".join(result.degraded) or None,
            detail={
                "origin_channel": req.origin_channel.value,
                "resolved_action_id": result.resolved_action_id,
                "hermes_run_id": result.hermes_run_id,
                "requires_approval": result.requires_approval,
            },
        )
        if result.status not in ("accepted", "in_flight"):
            instruments.record_error(f"command_{result.status}", result.degraded[0] if result.degraded else "none")