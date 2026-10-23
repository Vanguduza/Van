"""Paired-device API for state-bound, native-journaled owner recoveries."""
import asyncio
import json
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt, Field

from van_gateway.approval.service import OwnerApprovalError
from van_gateway.auth.service import AuthError
from van_gateway.trading.strategies import owner_authority_key_id
from van_gateway.trading.accounts import _trading_path
_trading_path()
from vati.app.runtime_control_protocol import ACTIONS, RecoveryIntent, RecoveryProof, RuntimeControlError
from vati.risk.contracts import KillSwitchTrigger


class RuntimeRecoveryIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['vati.runtime-recovery/1'] = Field(alias='schema')
    device_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')
    account_alias: str = Field(pattern=r'^[a-z0-9_]{3,32}$')
    session_id: str = Field(min_length=1, max_length=384)
    action: Literal['clear_kill_switch','reset_loss_streak','resume_drawdown']
    state_ref: str = Field(pattern=r'^[0-9a-f]{64}$')
    issued_at_unix: StrictInt = Field(ge=0)
    args: dict[str, str]


class RuntimeRecoveryChallengeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    intent: RuntimeRecoveryIntent


class RuntimeRecoveryApprovalProof(BaseModel):
    model_config = ConfigDict(extra='forbid')
    challenge_id: str
    signature_b64: str
    algorithm: Literal['ECDSA_P256_SHA256']
    expires_at_unix: StrictInt


class RuntimeRecoveryRequest(RuntimeRecoveryChallengeRequest):
    approval_proof: RuntimeRecoveryApprovalProof


class RuntimeLossScope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    losses: int
    cooldown_until_ms: int
    probation: bool
    suspended: bool
    cooldowns: list[int]


class RuntimeRecoveryState(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['vati.runtime-recovery-state/1'] = Field(alias='schema')
    account_alias: str
    session_id: str
    lease_epoch: int | None
    holder_instance_id: str
    profile_ref: str
    mandate_ref: str
    effective_mandate_ref: str
    kill_switch: list[KillSwitchTrigger]
    kill_history_ref: str
    owner_halt_refs: list[str]
    loss_scopes: dict[str, RuntimeLossScope]
    peak_equity: str
    risk_history_issue: str
    risk_control_refs: list[str]
    unresolved_entry_ids: list[str]


class RuntimeRecoveryReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    state: RuntimeRecoveryState
    state_ref: str
    observed_ms: int


class RuntimeRecoveryChallengeResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approval_challenge_id: str
    approval_challenge: str
    approval_expires_at_unix: int
    resolved_action_id: str
    intent: RuntimeRecoveryIntent
    resolved_review: RuntimeRecoveryReview


class RuntimeRecoveryResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason_code: Literal['APPLIED','APPROVAL_EXPIRED','OWNER_KEY_UNREGISTERED','SESSION_CHANGED',
        'STATE_CHANGED','PRECONDITION_UNMET','ACTOR_LEASE_LOST']
    effect_refs: list[str]
    entry_authority_granted: Literal[False]
    remaining_kill: list[KillSwitchTrigger] | None
    state_ref: str | None


class RuntimeRecoveryOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_id: str
    phase: Literal['REQUESTED','APPLIED','REFUSED']
    intent: RuntimeRecoveryIntent
    authority_ref: str
    accepted_at_unix: int
    expires_at_unix: int
    native_event_ref: str
    result: RuntimeRecoveryResult | None


class RuntimeRecoveryPendingDispatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_id: str
    phase: Literal['PENDING_DISPATCH']
    intent: RuntimeRecoveryIntent
    native_effect_confirmed: Literal[False]


class RuntimeRecoveryUnknown(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_id: str
    phase: Literal['UNKNOWN']
    reconciliation_required: Literal[True]
    readback_route: str


class RuntimeRecoveryCatalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['vati.runtime-recovery-catalog/1'] = Field(alias='schema')
    actions: list[Literal['clear_kill_switch','reset_loss_streak','resume_drawdown']]
    argument_schemas: dict[str, dict]
    requires_owner_approval: Literal[True]
    original_operation_id: Literal['approval_challenge_id']
    native_phases: list[str]
    gateway_phases: list[str]
    applied_is_entry_permission: Literal[False]
    supported_runtime: Literal['single-session']
    state_route: str
    operation_route: str


def register_runtime_control_routes(app, *, auth, store, promotions, audit):
    async def device(request):
        identity = getattr(request.state, 'van_device_id', None)
        if not identity:
            raise HTTPException(403, 'paired owner device required')
        try:
            await auth.require_device(identity)
        except AuthError as exc:
            raise HTTPException(403, exc.message) from exc
        return identity

    async def run(name, args):
        if promotions.control is None:
            raise HTTPException(503, 'runtime recovery requires the private van-trading commander')
        return await asyncio.to_thread(promotions.control.run, name, args)

    def parse(body, identity):
        try:
            intent = RecoveryIntent.from_mapping(body.model_dump(by_alias=True))
        except RuntimeControlError as exc:
            raise HTTPException(422, str(exc)) from exc
        if intent.device_id != identity:
            raise HTTPException(403, 'device_identity_mismatch')
        return intent

    async def receipt(operation_id, identity):
        row = await store.fetchone('SELECT value FROM runtime_meta WHERE key=?', ('owner_approval_receipt:'+operation_id,))
        if row is None:
            return None
        try:
            value = json.loads(row['value'])
        except (ValueError, TypeError) as exc:
            raise HTTPException(503, 'original recovery receipt is unreadable') from exc
        return value if value.get('device_id') == identity else None

    async def original(operation_id, identity):
        try:
            return await run('runtime_recovery_operation', {'operation_id': operation_id, 'device_id': identity})
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return None

    @app.get('/v1/trading/runtime/recovery/catalog', response_model=RuntimeRecoveryCatalog)
    async def runtime_recovery_catalog(request: Request):
        await device(request)
        return {'schema':'vati.runtime-recovery-catalog/1', 'actions': sorted(ACTIONS),
            'argument_schemas':{
                'clear_kill_switch':{'type':'object','required':['trigger'],'additionalProperties':False,
                    'properties':{'trigger':{'type':'string','enum':[t.value for t in KillSwitchTrigger]}}},
                'reset_loss_streak':{'type':'object','required':['scope'],'additionalProperties':False,
                    'properties':{'scope':{'type':'string','description':'*ACCOUNT* or an existing strategy scope'}}},
                'resume_drawdown':{'type':'object','additionalProperties':False}},
            'requires_owner_approval': True, 'original_operation_id': 'approval_challenge_id',
            'native_phases':['REQUESTED','APPLIED','REFUSED'],
            'gateway_phases':['PENDING_DISPATCH','UNKNOWN'],
            'applied_is_entry_permission':False, 'supported_runtime':'single-session',
            'state_route':'/v1/trading/runtime/recovery/state',
            'operation_route':'/v1/trading/runtime/recovery/operations/{operation_id}'}

    @app.get('/v1/trading/runtime/recovery/state', response_model=RuntimeRecoveryReview)
    async def runtime_recovery_state(request: Request, account_alias: str, session_id: str):
        await device(request)
        return await run('runtime_recovery_review', {'account_alias':account_alias, 'session_id':session_id})

    @app.post('/v1/trading/runtime/recovery/challenge', response_model=RuntimeRecoveryChallengeResponse)
    async def runtime_recovery_challenge(request: Request, req: RuntimeRecoveryChallengeRequest):
        identity = await device(request); intent = parse(req.intent, identity)
        review = await run('runtime_recovery_review', {'account_alias':intent.account_alias, 'session_id':intent.session_id})
        if review.get('state_ref') != intent.state_ref:
            raise HTTPException(409, 'native recovery state changed; review again')
        challenge = await app.state.orchestrator.approvals.issue(device_id=identity,
            source_command_id='runtime:'+intent.action, turn_id=None,
            action_id=intent.action_id, text=intent.approval_text, project_id=None)
        return {'approval_challenge_id':challenge.challenge_id, 'approval_challenge':challenge.canonical,
            'approval_expires_at_unix':challenge.expires_at_unix, 'resolved_action_id':intent.action_id,
            'intent':intent.body(), 'resolved_review':review}

    @app.get('/v1/trading/runtime/recovery/operations/{operation_id}',
        response_model=RuntimeRecoveryOperation | RuntimeRecoveryPendingDispatch)
    async def runtime_recovery_operation(request: Request, operation_id: str):
        identity = await device(request)
        native = await original(operation_id, identity)
        if native is not None:
            return native
        saved = await receipt(operation_id, identity)
        if saved is None:
            raise HTTPException(404, 'unknown original recovery operation')
        # Reading never dispatches or clears anything. An original POST can
        # resume its durable exact-operation dispatch; no new approval/ID.
        return {'operation_id':operation_id, 'phase':'PENDING_DISPATCH',
            'intent':saved['context']['intent'], 'native_effect_confirmed':False}

    @app.post('/v1/trading/runtime/recovery/request', response_model=RuntimeRecoveryOperation,
        responses={503:{'model':RuntimeRecoveryUnknown}})
    async def runtime_recovery_request(request: Request, req: RuntimeRecoveryRequest):
        identity = await device(request); intent = parse(req.intent, identity)
        supplied = req.approval_proof
        row = await store.fetchone('SELECT public_key_pem FROM devices WHERE device_id=? AND revoked_at_unix IS NULL', (identity,))
        if row is None:
            raise HTTPException(403, 'owner device is revoked')
        key_id = owner_authority_key_id(row['public_key_pem'])
        proof = RecoveryProof(supplied.challenge_id, supplied.expires_at_unix, key_id, supplied.signature_b64, supplied.algorithm)
        context = {'intent':intent.body(), 'proof':proof.public_record()}
        saved = await receipt(proof.operation_id, identity)
        if saved is not None:
            if saved.get('context') != context:
                raise HTTPException(409, 'original recovery actor or target differs')
        else:
            import time
            try:
                proof.verify(intent, {key_id:row['public_key_pem']}, now_unix=int(time.time()))
                await app.state.orchestrator.approvals.verify_and_consume(
                    challenge_id=proof.operation_id, source_command_id='runtime:'+intent.action,
                    signature_b64=proof.signature_b64, device_id=identity, turn_id=None,
                    action_id=intent.action_id, text=intent.approval_text, project_id=None,
                    durable_receipt=context)
            except (OwnerApprovalError, RuntimeControlError) as exc:
                # A concurrent identical POST may have committed the SAME
                # receipt. It cannot authorize a different operation or body.
                saved = await receipt(proof.operation_id, identity)
                if saved is None or saved.get('context') != context:
                    raise HTTPException(403, str(exc)) from exc
        try:
            native = await original(proof.operation_id, identity)
            if native is not None:
                return native
            await asyncio.to_thread(promotions.ensure_owner_authority,
                device_id=identity, public_key_pem=row['public_key_pem'])
            result = await run('runtime_recovery_request', context)
        except HTTPException:
            # No assertion of failure/cancellation after a potentially accepted
            # native enqueue. The original ID is durable before network IO.
            return JSONResponse(status_code=503, content={'operation_id':proof.operation_id,
                'phase':'UNKNOWN', 'reconciliation_required':True,
                'readback_route':'/v1/trading/runtime/recovery/operations/'+proof.operation_id})
        await audit.record(result='runtime_recovery_requested', device_id=identity,
            capability=intent.action_id, approval=proof.operation_id, after={'phase':result.get('phase')})
        return result
