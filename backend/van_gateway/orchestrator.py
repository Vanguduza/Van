from __future__ import annotations

import time
from typing import Any

from van_gateway.approval.service import OwnerApprovalError, OwnerApprovalService
from van_gateway.audit.service import AuditService
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.auth.throttle import AuthThrottle, Throttled
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityRecord, CommandAuthorityService
from van_gateway.command.ingress_trust import derive_effective_trust
from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.command.nonce import CommandNonceService, NonceReplay
from van_gateway.command.resolver import ResolutionMode, TypedCommandResolver
from van_gateway.context.service import OwnerContextService
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.hermes.bridge import HermesBridge, HermesBridgeError
from van_gateway.idempotency.service import IdempotencyConflict, IdempotencyInFlight, IdempotencyService
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
            and not req.no_stale_replay
        )

    async def handle(self, req: CommandRequest) -> CommandResult:
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


        # The nonce is covered by the v2 signature and, until now, was never stored — so a
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

        if effective_action_class == ActionClass.A5:
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="A5 prohibited action",
            )
            await self.audit.record(result="denied", command_id=req.command_id, device_id=req.device_id, failure_reason="A5")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        owner_approved = False
        if effective_action_class == ActionClass.A4:
            if resolution.mode != ResolutionMode.EXACT_ACTION or not resolution.action_id:
                result = CommandResult(
                    status="denied",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="A4 requires an exact gateway-resolved action before owner approval",
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
                    message="A4 requires biometric owner approval bound to the paired device key",
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

        try:
            context_snapshot = await self.context.compile_snapshot(
                req.command_id,
                [],
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
        canonical_context = {
            "snapshot_id": context_snapshot.snapshot_id,
            "digest": context_snapshot.digest,
            "kernel_revision": context_snapshot.kernel_revision,
            "fact_ids": context_snapshot.fact_ids,
            "live_state_refs": context_snapshot.live_state_refs,
            "policy_refs": context_snapshot.policy_refs,
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
            run = await self.hermes.create_run(
                req.text,
                metadata={
                    "command_id": req.command_id,
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
                    "no_stale_replay": effective_no_stale_replay,
                    "client_context": req.client_context,
                    "client_context_authoritative": False,
                    "canonical_context": canonical_context,
                    "typed_resolution": resolution.model_dump(mode="json"),
                    "gateway_action_authority_required": True,
                    "owner_approved": owner_approved,
                },
            )
        except HermesBridgeError as exc:
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
        )
        await self.idempotency.complete(req.idempotency_key, result.model_dump())
        return result