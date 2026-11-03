"""Native account-effect identities in the existing VATI authority ledger.

No network exactly-once assumption: a committed attempt is never reopened by
timeout/restart. Callers supply native-authorized identity and public outcomes;
this journal does not create owner authority or store credential values.
"""
from dataclasses import asdict, dataclass
from contextvars import ContextVar
import json
import hmac
import hashlib
import re
import time

from fastapi import HTTPException

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

PRODUCER = "vati-native-account-control"
SCHEMA = "vati.native-account-operation/1"
JOURNALED_COMMANDS = frozenset({"account_upsert", "account_credentials", "account_remove", "mt5_ea_issue_key", "deriv_create_demo", "account_restrict"})
_effect_started = ContextVar("native_account_effect_started", default=None)


def mark_account_effect(*, require_current=False):
    """Called immediately before native registry/credential effects, never after."""
    marker = _effect_started.get()
    if marker is not None:
        if require_current:require_current_account_effect()
        marker[0] = True


def require_current_account_effect():
    """Recheck consumed authority at a protected account effect or provider send."""
    marker = _effect_started.get()
    if marker is None:
        raise HTTPException(403, "Verified original account operation is required before provider dispatch")
    if marker[2] is not None:
        marker[2]()
    if int(time.time()) >= marker[1].expires_at_unix:
        raise HTTPException(403, "Original owner authority expired before provider dispatch; no effect started")


def operation_intent(command, args, *, digest_key=None):
    raw = args.get("_native_operation")
    if not isinstance(raw, dict):
        raise AccountEffectError("verified native account operation is required")
    values = {key: value for key, value in args.items() if not key.startswith("_")}
    alias = str(values.get("alias", "")).strip().lower()
    targets = ("account:" + alias,)
    domain=args.get('_expected_account_control_domain')
    if domain is not None:
        if not isinstance(domain,str) or not re.fullmatch(r'[0-9a-f]{64}',domain):
            raise AccountEffectError('Native account-control namespace is invalid')
        targets+=('account-control-domain:'+domain,)
    if command == "deriv_create_demo":
        # This native owner/state namespace has no verified remote customer
        # identity before provisioning. All its unresolved Deriv creations
        # overlap. Caller email, code, app ID, device, alias or profile labels
        # cannot prove another remote customer is independent. A separately
        # admitted native owner/provider has its own journal.
        targets += ("deriv-demo-provisioning",)
        if digest_key is not None:
            targets += ("deriv-demo-key:" + hashlib.sha256(digest_key).hexdigest(),)
    request_digest = canonical_hash(values)
    if raw.get("request_digest") != request_digest:
        raise AccountEffectConflict("native operation request differs from its verified dispatch")
    if command == "deriv_create_demo" and digest_key is not None:
        request_digest = hmac.new(digest_key, request_digest.encode(), hashlib.sha256).hexdigest()
    authority_ref=raw.get('authority_ref')
    if command=='deriv_create_demo' and digest_key is not None:
        if not isinstance(authority_ref,str) or not authority_ref:
            raise AccountEffectError('Original authenticated request reference is required')
        # The A4 reference can itself commit to a secret-bearing request.
        # Persist its keyed reference, never an offline-guessable commitment.
        authority_ref=hmac.new(digest_key,('authority-ref:'+authority_ref).encode(),hashlib.sha256).hexdigest()
    intent = AccountEffectIntent(
        operation_id=raw.get("operation_id"), device_id=raw.get("device_id"),
        authority_ref=authority_ref, command=command,
        targets=targets, request_digest=request_digest,
        resource_version=args.get("_expected_resource_version"),
        expires_at_unix=raw.get("expires_at_unix"))
    intent.validate()
    return intent


def targets_overlap(left, right):
    # Key fingerprints attest vault continuity, not a shared mutable subject.
    a = {target for target in left if not target.startswith(('deriv-demo-key:','account-control-domain:'))}
    b = {target for target in right if not target.startswith(('deriv-demo-key:','account-control-domain:'))}
    return bool(a.intersection(b))


def public_account_result(command, result):
    # Signing material remains in its existing native vault. Readback confirms
    # the ORIGINAL issue; it never issues a second key or retains an export.
    if command == "mt5_ea_issue_key":
        return {"account": result["account"], "credential_export_available": False,
                "note": "Original key issue is confirmed; credential values are not retained in operation history"}
    return result


class AccountEffectError(ValueError):
    pass


class AccountEffectUnknown(AccountEffectError):
    pass


class AccountEffectConflict(AccountEffectError):
    pass


class AccountEffectAuthorityExpired(AccountEffectError):
    pass


class AccountOperationUnconfirmed(HTTPException):
    effect_state = "UNKNOWN"
    reconciliation_required = True

    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__(409, {"code": "account_operation_unconfirmed", "operation_id": operation_id,
                              "message": "Read the original native operation; do not repeat its effects"})


class AccountOperationBlocked(HTTPException):
    reconciliation_required = True

    def __init__(self, detail=None):
        super().__init__(409, detail or "Account target has an unconfirmed original native operation; reconciliation required")


def readback(state):
    return {"operation_id": state.intent.operation_id, "action": state.intent.command,
            "effect_state": state.phase if state.phase in {"APPLIED", "REFUSED"} else "UNKNOWN",
            "native_phase": state.phase, "reconciliation_required": state.phase in {"IN_FLIGHT", "UNKNOWN"},
            "result": state.result, "native_event_ref": state.event_ref,
            'account_control_domain':next((target.split(':',1)[1] for target in state.intent.targets
                if target.startswith('account-control-domain:')),None)}


def invoke_account_effect(journal, intent, handler, *, dispatch_guard=None,qualified_cleanup_parent=None):
    """Caller holds the alias fence; no ledger transaction spans the handler."""
    try:
        claim = (journal.claim(intent) if qualified_cleanup_parent is None
                 else journal.claim_cleanup(intent,qualified_cleanup_parent))
    except AccountEffectConflict:
        raise AccountOperationBlocked() from None
    except AccountEffectUnknown:
        raise AccountOperationUnconfirmed(intent.operation_id) from None
    except AccountEffectAuthorityExpired:
        raise HTTPException(403, "Original owner authority expired before native dispatch; no effect started") from None
    if claim.phase == "APPLIED":
        return claim.result
    if claim.phase == "REFUSED":
        raise HTTPException(claim.result["status_code"], claim.result["detail"])
    marker = [False, intent, dispatch_guard]
    context = _effect_started.set(marker)
    try:
        result = handler()
        journal.complete(claim, public_account_result(intent.command, result))
        return result
    except BaseException as exc:
        try:
            # A failed reply/commit acknowledgement cannot override a durable
            # completion, and a failed completion cannot reopen an attempt.
            current = journal.status(intent.operation_id, intent.device_id)
            if current and current.phase == "APPLIED":
                return current.result
            if not marker[0] and isinstance(exc, HTTPException) and 400 <= exc.status_code < 500:
                journal.refuse(claim, exc.status_code)
                raise exc
            journal.uncertain(claim)
        except HTTPException:
            raise
        except Exception:
            pass  # IN_FLIGHT itself is a persistent fence when UNKNOWN cannot be recorded.
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise AccountOperationUnconfirmed(intent.operation_id) from None
    finally:
        _effect_started.reset(context)


@dataclass(frozen=True)
class AccountEffectIntent:
    operation_id: str
    device_id: str
    authority_ref: str
    command: str
    targets: tuple[str, ...]
    request_digest: str
    resource_version: str
    expires_at_unix: int

    def validate(self):
        if not isinstance(self.operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", self.operation_id):
            raise AccountEffectError("native operation identity is invalid")
        if not all(isinstance(v, str) and v for v in (self.device_id, self.authority_ref, self.command)):
            raise AccountEffectError("native operation authority and actor are required")
        if not self.targets or not isinstance(self.targets, tuple) or len(self.targets) > 64 or any(
            not isinstance(v, str) or not v or len(v) > 256 for v in self.targets
        ) or len(set(self.targets)) != len(self.targets):
            raise AccountEffectError("native operation target scope is invalid")
        if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in (self.request_digest, self.resource_version)):
            raise AccountEffectError("native operation input binding is invalid")
        if type(self.expires_at_unix) is not int:
            raise AccountEffectError("native operation authority expiry is required")


@dataclass(frozen=True)
class AccountEffectState:
    intent: AccountEffectIntent
    phase: str
    event_ref: str
    result: dict | None = None


@dataclass(frozen=True)
class RestrictionResolutionQualification:
    """Validated DATA only; the native controller must independently authorize."""
    parent_id: str
    parent_ref: str
    parent_hash: str
    child_hash: str
    summary_json: str
    child_request_json: str
    evidence_json: str

    @property
    def summary(self):
        return json.loads(self.summary_json)

    @property
    def operation_refs(self):
        return json.loads(self.evidence_json)['operation_refs']


class AccountEffectJournal:
    def __init__(self, ledger, *, cleanup_secrets_root=None):
        self.ledger = ledger
        self.cleanup_secrets_root=cleanup_secrets_root

    @staticmethod
    def internal_namespace_metadata(event):
        p=event.payload
        if p.get('record_type')!='INTERNAL_NAMESPACE_METADATA':return False
        if (event.producer!=PRODUCER or p.get('schema')!=SCHEMA
            or set(p)!={'schema','record_type','account_control_domain','legacy_originals_bound','authority_issued'}
            or not isinstance(p.get('account_control_domain'),str)
            or not re.fullmatch(r'[0-9a-f]{64}',p['account_control_domain'])
            or p.get('legacy_originals_bound') is not False or p.get('authority_issued') is not False):
            raise AccountEffectUnknown('Native account-control internal metadata is ambiguous')
        return True

    def business_events(self):
        self._states()  # Validate the complete protected chain and both variants.
        return [event for event in self.ledger.iter(EventKind.ACCOUNT_OPERATION)
            if not self.internal_namespace_metadata(event) and event.payload.get('record_type')!='RESTRICTION_RESOLUTION']

    def _states(self):
        if not self.ledger.verify_chain()[0]:
            raise AccountEffectUnknown("native account operation history failed integrity verification")
        states = {}
        resolutions = {}
        for event in self.ledger.iter(EventKind.ACCOUNT_OPERATION):
            try:
                if self.internal_namespace_metadata(event):continue
                p = event.payload
                if p.get('record_type')=='RESTRICTION_RESOLUTION':
                    self._validate_restriction_record(event,states,resolutions)
                    resolutions[p['parent_id']]=p
                    continue
                if event.producer != PRODUCER or p.get("schema") != SCHEMA:
                    raise ValueError
                raw = p["intent"]
                intent = AccountEffectIntent(**{**raw, "targets": tuple(raw["targets"])})
                intent.validate()
                if p["intent_hash"] != canonical_hash(asdict(intent)) or event.correlation_id != intent.operation_id:
                    raise ValueError
                previous = states.get(intent.operation_id)
                if previous is None:
                    if p["phase"] != "IN_FLIGHT" or p.get("previous_ref") != "" or p.get("result") is not None:
                        raise ValueError
                else:
                    if previous.phase != "IN_FLIGHT" or previous.intent != intent or p.get("previous_ref") != previous.event_ref:
                        raise ValueError
                    if p["phase"] not in {"APPLIED", "UNKNOWN", "REFUSED"}:
                        raise ValueError
                result = p.get("result")
                if p["phase"] in {"APPLIED", "REFUSED"}:
                    self._public_result(result)
                    if p["phase"] == "REFUSED" and (set(result) != {"status_code", "detail"}
                        or type(result["status_code"]) is not int or not 400 <= result["status_code"] < 500
                        or not isinstance(result["detail"], str)):
                        raise ValueError
                elif result is not None:
                    raise ValueError
                states[intent.operation_id] = AccountEffectState(intent, p["phase"], event.hash, result)
            except (KeyError, TypeError, ValueError):
                raise AccountEffectUnknown("native account operation history is ambiguous; reconcile original effects") from None
        return states

    @staticmethod
    def _restriction_original_request(value):
        if not isinstance(value,dict) or value.get('variant') not in {'RESTRICT','BEGIN_REAUTH','COMPLETE_REAUTH','RECONCILE_DATA'}:
            raise AccountEffectConflict('Restriction original request is invalid')
        if value['variant']=='RECONCILE_DATA':
            AccountEffectJournal._restriction_child_request(value,value.get('parent_operation_id'),value.get('alias'))
            if not {'reauth_fact_id','reauth_fact_digest'}<=set(value):
                raise AccountEffectConflict('Restriction original reconciliation fact is absent')
            return
        base={'alias','variant'};identity={'restriction_id','expected_revision','expected_digest'}
        if value['variant']=='RESTRICT':
            allowed=base|{'reason_code'}
            if set(value)!=allowed and set(value)!=allowed|identity:raise AccountEffectConflict('Restriction original fields differ')
            if value['reason_code'] not in {'OWNER_REQUEST','CREDENTIALS_EXPIRED','BROKER_DISABLED','KILL_SWITCH','VERIFICATION_FAILED'}:
                raise AccountEffectConflict('Restriction original reason differs')
        elif set(value)!=base|identity|{'reauth_fact_id','reauth_fact_digest'}:
            raise AccountEffectConflict('Restriction recovery fields differ')
        if not isinstance(value['alias'],str) or re.fullmatch(r'[a-z0-9_]{3,32}',value['alias']) is None:
            raise AccountEffectConflict('Restriction original alias is invalid')
        if 'restriction_id' in value:
            if (not isinstance(value['restriction_id'],str) or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',value['restriction_id']) is None
                    or type(value['expected_revision']) is not int or value['expected_revision']<1
                    or not isinstance(value['expected_digest'],str) or re.fullmatch(r'[0-9a-f]{64}',value['expected_digest']) is None):
                raise AccountEffectConflict('Restriction original revision is invalid')
        if 'reauth_fact_id' in value:
            if (not isinstance(value['reauth_fact_id'],str) or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',value['reauth_fact_id']) is None
                    or not isinstance(value['reauth_fact_digest'],str) or re.fullmatch(r'[0-9a-f]{64}',value['reauth_fact_digest']) is None):
                raise AccountEffectConflict('Restriction original fact is invalid')

    @staticmethod
    def _restriction_admission_shape(value):
        fields={'schema','owner_id','device_id','operation_id','reauth_purpose','actor_key_ref','context','request_digest',
                'reauth_fact_digest','reauth_proof_ref','created_at_unix','expires_at_unix','authority_ref',
                'approval_text_digest','approval_parameters_digest','reauth_fact_id','state','action','purpose',
                'native_request','native_review','native_review_digest','admission_digest'}
        if not isinstance(value,dict) or set(value)!=fields:raise AccountEffectConflict('Restriction admission fields differ')
        context=value['context']
        if not isinstance(context,dict) or set(context)!={'alias','restriction_id','incarnation','account_control_domain','original_device_id',
                'review_digest','resource_version','variant','semantic_digest','expected_revision','expected_digest','reason_code',
                'parent_operation_id','parent_admission_digest'}:raise AccountEffectConflict('Restriction admission context fields differ')
        for key in ('actor_key_ref','request_digest','authority_ref','approval_text_digest','approval_parameters_digest','native_review_digest','admission_digest'):
            if not isinstance(value[key],str) or re.fullmatch(r'[0-9a-f]{64}',value[key]) is None:
                raise AccountEffectConflict('Restriction admission binding invalid')
        for key in ('incarnation','account_control_domain','review_digest','resource_version','semantic_digest'):
            if not isinstance(context[key],str) or re.fullmatch(r'[0-9a-f]{64}',context[key]) is None:
                raise AccountEffectConflict('Restriction admission context binding invalid')
        if (value['state']!='ADMITTED_NOT_NATIVE_COMPLETION' or type(value['created_at_unix']) is not int
                or type(value['expires_at_unix']) is not int or not 0<value['created_at_unix']<value['expires_at_unix']
                or not isinstance(value['device_id'],str) or not 1<=len(value['device_id'])<=128
                or re.search(r'(?i)(password|token|api[_-]?key)\s*[:=]',value['device_id']) is not None
                or context['reason_code'] not in {'OWNER_REQUEST','CREDENTIALS_EXPIRED','BROKER_DISABLED','KILL_SWITCH','VERIFICATION_FAILED'}):
            raise AccountEffectConflict('Restriction admission metadata invalid')
        if context['variant']=='RECONCILE_DATA':
            if (not isinstance(context['parent_operation_id'],str) or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',context['parent_operation_id']) is None
                    or not isinstance(context['parent_admission_digest'],str) or re.fullmatch(r'[0-9a-f]{64}',context['parent_admission_digest']) is None):
                raise AccountEffectConflict('Restriction reconciliation parent binding invalid')
        elif context['parent_operation_id'] is not None or context['parent_admission_digest'] is not None:
            raise AccountEffectConflict('Restriction unexpected parent binding')
        for key in ('reauth_fact_digest','reauth_proof_ref'):
            if value[key] is not None and (not isinstance(value[key],str) or re.fullmatch(r'[0-9a-f]{64}',value[key]) is None):
                raise AccountEffectConflict('Restriction admission reauthentication invalid')
        if value['reauth_fact_id'] is not None and (not isinstance(value['reauth_fact_id'],str)
                or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',value['reauth_fact_id']) is None):
            raise AccountEffectConflict('Restriction admission fact identity invalid')
        if value['reauth_purpose'] not in {None,'ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA'}:
            raise AccountEffectConflict('Restriction admission purpose invalid')
        if value['request_digest']!=canonical_hash({'context':context,'fact_id':value['reauth_fact_id'],
                'challenge_id':value['operation_id'],'text_digest':value['approval_text_digest'],
                'parameters_digest':value['approval_parameters_digest']}):
            raise AccountEffectConflict('Restriction admission request binding invalid')
        review=value['native_review'];request=value['native_request']
        if (not isinstance(review,dict) or set(review)!={'schema','semantic_digest','resource_version','view','context_digest','request_digest','review_digest'}
                or review['schema']!='vati.account-restriction-review/1' or not isinstance(review['view'],dict)
                or review['review_digest']!=value['native_review_digest']
                or review['review_digest']!=canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
                or review['context_digest']!=context['review_digest']
                or review['context_digest']!=canonical_hash({k:v for k,v in review.items() if k not in {'review_digest','request_digest','context_digest'}})
                or review['request_digest']!=canonical_hash(request) or review['semantic_digest']!=context['semantic_digest']
                or review['resource_version']!=context['resource_version']
                or value['approval_parameters_digest']!=canonical_hash({'restriction_review':review,'native_request':request,'reauth_fact_digest':value['reauth_fact_digest']})):
            raise AccountEffectConflict('Restriction native review binding invalid')
        view=review['view']
        fields={'alias','owner_device_id','account_control_domain','restriction_id','incarnation','expected_revision','expected_digest',
                'reason_code','before','enabled','mode','mode_or_mandate_granted','entry_permitted','protective_exits_preserved',
                'native_identity_required','native_identity_scope_ref','parent_admission_digest','related_operations'}
        if (set(view)!=fields or view['alias']!=context['alias'] or view['owner_device_id']!=value['device_id']
                or any(view[k]!=context[k] for k in ('account_control_domain','restriction_id','incarnation','expected_revision','expected_digest','reason_code','parent_admission_digest'))
                or type(view['enabled']) is not bool or view['mode'] not in {'OBSERVE','ADVISOR','DEMO_TRADER','SHADOW_TRADER','LIMITED_LIVE','AUTONOMOUS_LIVE'}
                or view['mode_or_mandate_granted'] is not False or view['entry_permitted'] is not False
                or view['protective_exits_preserved'] is not True or type(view['native_identity_required']) is not bool
                or view['native_identity_required'] is not (context['variant']=='COMPLETE_REAUTH')
                or (view['native_identity_required'] and (not isinstance(view['native_identity_scope_ref'],str)
                    or re.fullmatch(r'[0-9a-f]{64}',view['native_identity_scope_ref']) is None))
                or (not view['native_identity_required'] and view['native_identity_scope_ref'] is not None)
                or not isinstance(view['related_operations'],list) or len(view['related_operations'])>64):
            raise AccountEffectConflict('Restriction native review scope invalid')
        before=view['before']
        if context['expected_revision']==0:
            if before is not None:raise AccountEffectConflict('Restriction native review preimage invalid')
        else:
            from vati.accounts.restrictions import REASON_TEXT, TRANSITION_TEXT
            keys={'schema','alias','restriction_id','incarnation','device_id','account_control_domain','revision','phase','reason_code',
                  'reason','created_at_unix','updated_at_unix','record_digest','entry_permitted','mode_or_mandate_granted',
                  'protection_or_manual_exit_cancelled','transition_reason','prior_phase_observation'}
            if (not isinstance(before,dict) or set(before)!=keys or before['schema']!='vati.account-restriction/1'
                    or before['alias']!=context['alias'] or before['restriction_id']!=context['restriction_id']
                    or before['incarnation']!=context['incarnation'] or before['device_id']!=value['device_id']
                    or before['account_control_domain']!=context['account_control_domain']
                    or before['revision']!=context['expected_revision'] or before['record_digest']!=context['expected_digest']
                    or before['reason_code']!=context['reason_code'] or before['reason']!=REASON_TEXT[context['reason_code']]
                    or before['phase'] not in {'RESTRICTED','REAUTH_PENDING','LINKED_READ_ONLY'}
                    or before['transition_reason'] not in set(TRANSITION_TEXT.values())|{before['reason']}
                    or before['entry_permitted'] is not False or before['mode_or_mandate_granted'] is not False
                    or before['protection_or_manual_exit_cancelled'] is not False
                    or type(before['created_at_unix']) is not int or type(before['updated_at_unix']) is not int):
                raise AccountEffectConflict('Restriction native review preimage invalid')
            prior=before['prior_phase_observation']
            if (not isinstance(prior,dict) or type(prior.get('observed')) is not bool
                    or (prior.get('observed') is False and (set(prior)!={'observed','reason','source_ref'}
                        or prior['reason']!='PRIOR_CANONICAL_PHASE_NOT_OBSERVED'
                        or not isinstance(prior['source_ref'],str) or re.fullmatch(r'[0-9a-f]{64}',prior['source_ref']) is None))
                    or (prior.get('observed') is True and (set(prior)!={'observed','phase','proof_ref'}
                        or prior['phase'] not in {'LINKED_READ_ONLY','KYC_PENDING','ACTIVE_ELIGIBLE'}
                        or not isinstance(prior['proof_ref'],str) or re.fullmatch(r'[0-9a-f]{64}',prior['proof_ref']) is None))):
                raise AccountEffectConflict('Restriction native review prior observation invalid')
        AccountEffectJournal._public_result(view)

    @staticmethod
    def _restriction_child_request(value, parent_id, alias):
        required={'alias','variant','parent_operation_id','restriction_id','expected_revision'}
        optional={'expected_digest','reauth_fact_id','reauth_fact_digest'}
        if (not isinstance(value,dict) or not required<=set(value) or set(value)-required-optional
                or value['variant']!='RECONCILE_DATA' or value['parent_operation_id']!=parent_id
                or value['alias']!=alias or type(value['expected_revision']) is not int or value['expected_revision']<0
                or not isinstance(value['restriction_id'],str)
                or ('reauth_fact_id' in value)!=('reauth_fact_digest' in value)):
            raise AccountEffectConflict('Restriction reconciliation request is invalid')
        for key in ('expected_digest','reauth_fact_digest'):
            if key in value and (not isinstance(value[key],str) or re.fullmatch(r'[0-9a-f]{64}',value[key]) is None):
                raise AccountEffectConflict('Restriction reconciliation digest is invalid')
        if 'reauth_fact_id' in value and (not isinstance(value['reauth_fact_id'],str)
                or re.fullmatch(r'[A-Za-z0-9_-]{20,128}',value['reauth_fact_id']) is None):
            raise AccountEffectConflict('Restriction reconciliation fact identity is invalid')
        if (value['expected_revision']==0)!=('expected_digest' not in value):
            raise AccountEffectConflict('Restriction reconciliation revision is invalid')

    def _validate_restriction_record(self,event, states, resolutions):
        p=event.payload
        fields={'schema','record_type','parent_id','parent_ref','parent_hash','child_id','child_ref','child_hash','child_request','evidence','summary','summary_hash','authority_issued'}
        if (event.producer!=PRODUCER or set(p)!=fields or p['schema']!=SCHEMA
                or p['authority_issued'] is not False or p['parent_id'] in resolutions
                or event.correlation_id!=p['child_id'] or not isinstance(p['summary'],dict)
                or canonical_hash(p['summary'])!=p['summary_hash']):raise ValueError()
        parent=states.get(p['parent_id']);child=states.get(p['child_id'])
        if (parent is None or child is None or parent.phase not in {'IN_FLIGHT','UNKNOWN'}
                or child.phase not in {'IN_FLIGHT','UNKNOWN'} or parent.event_ref!=p['parent_ref']
                or child.event_ref!=p['child_ref'] or canonical_hash(asdict(parent.intent))!=p['parent_hash']
                or canonical_hash(asdict(child.intent))!=p['child_hash']
                or parent.intent.command!='account_restrict' or child.intent.command!='account_restrict'
                or parent.intent.device_id!=child.intent.device_id or parent.intent.targets!=child.intent.targets):raise ValueError()
        if (not isinstance(p['child_request'],dict) or canonical_hash(p['child_request'])!=child.intent.request_digest
                or p['child_request'].get('variant')!='RECONCILE_DATA'
                or p['child_request'].get('parent_operation_id')!=p['parent_id']):raise ValueError()
        AccountEffectJournal._restriction_child_request(p['child_request'],p['parent_id'],p['summary'].get('alias'))
        evidence=p['evidence']
        if not isinstance(evidence,dict) or set(evidence)!={'original_request','original_admission','observed_row','related_admissions','operation_refs'}:raise ValueError()
        # Re-run the same DATA qualification against the row sealed at this
        # event's position, never against a later mutable registry snapshot.
        from types import SimpleNamespace
        verifier=AccountEffectJournal.__new__(AccountEffectJournal)
        verifier._states=lambda:states
        verifier.ledger=self.ledger
        verifier._prior_resolutions=resolutions
        registry=SimpleNamespace(_restrictions={} if evidence['observed_row'] is None else {p['summary']['alias']:evidence['observed_row']})
        check=verifier.qualify_restriction_resolution(child.intent,parent_operation_id=p['parent_id'],
            child_request=p['child_request'],original_request=evidence['original_request'],
            original_admission=evidence['original_admission'],expected_admission_digest=p['summary']['admission_digest'],
            registry=registry,current_resource_version=p['summary']['resource_version'],
            related_admissions=evidence['related_admissions'],expected_operation_refs=evidence['operation_refs'])
        if check.summary!=p['summary'] or check.parent_ref!=p['parent_ref'] or check.parent_hash!=p['parent_hash']:raise ValueError()
        s=p['summary']
        if (set(s)!={'outcome','alias','restriction_id','incarnation','revision','record_digest','event_ref','admission_digest','resource_version','resolved_operations','selected_parent_operation_id','anchor_operation_id','anchor_outcome','anchor_event_ref'}
                or s['outcome'] not in {'TRANSITION_OBSERVED','CURRENT_PREIMAGE_OBSERVED'}
                or not isinstance(s['alias'],str) or 'account:'+s['alias'] not in parent.intent.targets
                or type(s['revision']) is not int or s['revision']<0
                or any(not isinstance(s[k],str) or re.fullmatch(r'[0-9a-f]{64}',s[k]) is None for k in ('admission_digest','resource_version'))
                or any(s[k] is not None and (not isinstance(s[k],str) or re.fullmatch(r'[0-9a-f]{64}',s[k]) is None) for k in ('incarnation','record_digest','event_ref'))):raise ValueError()

    def _restriction_resolutions(self):
        self._states()
        return {e.payload['parent_id']:e.payload for e in self.ledger.iter(EventKind.ACCOUNT_OPERATION)
                if e.payload.get('record_type')=='RESTRICTION_RESOLUTION'}

    def restriction_resolution(self,parent_operation_id,device_id):
        """Return recorded DATA after lost child acknowledgement; no new effect."""
        with self.ledger.atomic():
            states=self._states();parent=states.get(parent_operation_id)
            if parent is None:return None
            if parent.intent.device_id!=device_id:raise AccountEffectConflict('Restriction original belongs to another device')
            records=self._restriction_resolutions()
            matches=[p for p in records.values() if parent_operation_id in p['summary']['resolved_operations']
                     or parent_operation_id==p['child_id']]
            if len(matches)>1:raise AccountEffectUnknown('Restriction original has ambiguous resolution records')
            record=matches[0] if matches else None
            if record is None:return None
            event=next(e for e in self.ledger.iter(EventKind.ACCOUNT_OPERATION)
                       if e.payload==record)
            return {'resolution_ref':event.hash,'resolution_child_operation_id':record['child_id'],**record['summary']}

    def _restriction_bundle_refs(self,states,parent_id,original_admission,related_admissions):
        if not isinstance(related_admissions,(list,tuple)) or len(related_admissions)>63:
            raise AccountEffectConflict('Restriction causal bundle is invalid')
        admissions=[original_admission,*related_admissions];by_id={}
        for admission in admissions:
            self._restriction_admission_shape(admission)
            op=admission['operation_id'];state=states.get(op)
            if (op in by_id or state is None or state.phase not in {'IN_FLIGHT','UNKNOWN','APPLIED','REFUSED'}
                    or state.intent.command!='account_restrict' or admission['admission_digest']!=canonical_hash({k:v for k,v in admission.items() if k!='admission_digest'})
                    or admission['schema']!='van.account-restriction-admission/1' or admission['owner_id']!='owner'
                    or admission['action']!='account_restrict' or admission['purpose']!='ACCOUNT_RESTRICTION_CONTROL'
                    or canonical_hash(admission['native_request'])!=state.intent.request_digest
                    or admission['context']['variant']!=admission['native_request'].get('variant')
                    or admission['context']['expected_revision']!=admission['native_request'].get('expected_revision',0)
                    or admission['context']['expected_digest']!=admission['native_request'].get('expected_digest')
                    or admission['context']['restriction_id']!=(admission['native_request'].get('restriction_id') or 'proposed:'+state.intent.resource_version)
                    or admission['context']['semantic_digest']!=canonical_hash({k:v for k,v in admission['native_request'].items() if k not in {'reauth_fact_id','reauth_fact_digest'}})
                    or state.intent.device_id!=admission['device_id']
                    or state.intent.authority_ref!=admission['authority_ref']+'::review:'+admission['native_review_digest']):
                raise AccountEffectConflict('Restriction causal original differs')
            self._restriction_original_request(admission['native_request'])
            by_id[op]=admission
        if parent_id not in by_id or admissions[0]['operation_id']!=parent_id:
            raise AccountEffectConflict('Restriction causal root differs')
        anchors=[op for op,a in by_id.items() if a['native_request']['variant'] in {'RESTRICT','BEGIN_REAUTH','COMPLETE_REAUTH'}]
        if len(anchors)!=1:raise AccountEffectConflict('Restriction causal anchor is missing or ambiguous')
        anchor=anchors[0];root=by_id[anchor];root_state=states[anchor];refs=[]
        for op,admission in by_id.items():
            context=admission['context'];state=states[op];req=admission['native_request']
            if (state.intent.targets!=root_state.intent.targets or state.intent.device_id!=root_state.intent.device_id
                    or context['alias']!=root['context']['alias'] or context['account_control_domain']!=root['context']['account_control_domain']
                    or context['incarnation']!=root['context']['incarnation'] or context['original_device_id']!=state.intent.device_id
                    or context['resource_version']!=state.intent.resource_version):
                raise AccountEffectConflict('Restriction causal scope differs')
            if op!=anchor:
                prev=context['parent_operation_id']
                if (state.phase not in {'IN_FLIGHT','UNKNOWN'} or req.get('variant')!='RECONCILE_DATA' or prev not in by_id or prev==op
                        or req.get('parent_operation_id')!=prev or context['parent_admission_digest']!=by_id[prev]['admission_digest']
                        or admission['reauth_purpose']!='ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA'
                        or admission['reauth_fact_id']!=req['reauth_fact_id'] or admission['reauth_fact_digest']!=req['reauth_fact_digest']
                        or admission['reauth_proof_ref'] is None):
                    raise AccountEffectConflict('Restriction causal predecessor differs')
                seen={op};cursor=prev
                while cursor!=anchor:
                    if cursor in seen or cursor not in by_id:raise AccountEffectConflict('Restriction causal graph is cyclic or incomplete')
                    seen.add(cursor);cursor=by_id[cursor]['context']['parent_operation_id']
            refs.append({'operation_id':op,'intent_hash':canonical_hash(asdict(state.intent)),'event_ref':state.event_ref,
                         'request_digest':state.intent.request_digest,'authority_ref':state.intent.authority_ref,
                         'native_review_digest':admission['native_review_digest'],'admission_digest':admission['admission_digest'],
                         'alias':context['alias'],'incarnation':context['incarnation'],'device_id':state.intent.device_id,
                         'account_control_domain':context['account_control_domain'],'parent_operation_id':context['parent_operation_id'],
                         'parent_admission_digest':context['parent_admission_digest']})
        refs.sort(key=lambda item:item['operation_id'])
        current={ref['operation_id']:ref for ref in refs}
        for op,admission in by_id.items():
            historical=admission['native_review']['view']['related_operations']
            if op==anchor:
                if historical:raise AccountEffectConflict('Restriction original review contains unrelated operations')
                continue
            prior={};active={};resolved=set()
            for event in self.ledger.iter(EventKind.ACCOUNT_OPERATION):
                if event.correlation_id==op and event.payload.get('phase')=='IN_FLIGHT':break
                prior[event.hash]=event
                payload=event.payload
                if payload.get('record_type')=='RESTRICTION_RESOLUTION':
                    resolved.update(payload['summary']['resolved_operations']);resolved.add(payload['child_id'])
                elif payload.get('phase') in {'IN_FLIGHT','UNKNOWN','APPLIED','REFUSED'}:
                    active[event.correlation_id]=event
            if not historical or [r.get('operation_id') for r in historical]!=sorted({r.get('operation_id') for r in historical}):
                raise AccountEffectConflict('Restriction causal reviewed references invalid')
            for ref in historical:
                target=current.get(ref.get('operation_id')) if isinstance(ref,dict) else None
                event=prior.get(ref.get('event_ref')) if isinstance(ref,dict) else None
                if (target is None or set(ref)!=set(target) or any(ref[k]!=target[k] for k in target if k!='event_ref')
                        or event is None or event.correlation_id!=ref['operation_id']
                        or event.payload.get('phase') not in {'IN_FLIGHT','UNKNOWN'}
                        or event.payload.get('intent_hash')!=ref['intent_hash']):
                    raise AccountEffectConflict('Restriction causal reviewed event differs')
            if admission['context']['parent_operation_id'] not in {r['operation_id'] for r in historical}:
                raise AccountEffectConflict('Restriction causal review omitted its parent')
            overlapping={key for key,event in active.items() if key not in resolved
                         and event.payload['phase'] in {'IN_FLIGHT','UNKNOWN'}
                         and targets_overlap(state.intent.targets,tuple(event.payload['intent']['targets']))}
            if overlapping!={r['operation_id'] for r in historical}:
                raise AccountEffectConflict('Restriction causal review omitted an unresolved operation')
            if any(active[r['operation_id']].hash!=r['event_ref'] for r in historical):
                raise AccountEffectConflict('Restriction causal review event was stale at claim')
        return refs

    def restriction_operation_refs(self,parent_operation_id,original_admission,*,related_admissions=()):
        """Derive DATA refs from the protected journal and supplied Store records."""
        with self.ledger.atomic():
            return self._restriction_bundle_refs(self._states(),parent_operation_id,original_admission,related_admissions)

    def qualify_restriction_resolution(self, child_intent, *, parent_operation_id, child_request,
                                       original_request, original_admission, expected_admission_digest,
                                       registry, current_resource_version, related_admissions=(), expected_operation_refs=()):
        """Compare actual DATA; caller separately holds locks and verifies authority."""
        from vati.accounts.restrictions import validate_record
        child_intent.validate()
        if (child_intent.command!='account_restrict' or not isinstance(child_request,dict)
                or canonical_hash(child_request)!=child_intent.request_digest
                or child_request.get('variant')!='RECONCILE_DATA'
                or child_request.get('parent_operation_id')!=parent_operation_id):
            raise AccountEffectConflict('Restriction reconciliation child binding differs')
        states=self._states();parent=states.get(parent_operation_id)
        prior_resolutions=getattr(self,'_prior_resolutions',None)
        if prior_resolutions is None:prior_resolutions=self._restriction_resolutions()
        if any(parent_operation_id in p['summary']['resolved_operations'] or parent_operation_id==p['child_id']
               for p in prior_resolutions.values()):
            raise AccountEffectConflict('Restriction original already has a resolution; read the original')
        if (parent is None or parent.phase not in {'IN_FLIGHT','UNKNOWN'} or parent.intent.command!='account_restrict'
                or parent.intent.device_id!=child_intent.device_id or parent.intent.targets!=child_intent.targets
                or not isinstance(original_request,dict) or canonical_hash(original_request)!=parent.intent.request_digest):
            raise AccountEffectConflict('Restriction original intent differs')
        admission=original_admission
        self._restriction_original_request(original_request)
        self._restriction_admission_shape(admission)
        if (not isinstance(expected_admission_digest,str) or re.fullmatch(r'[0-9a-f]{64}',expected_admission_digest) is None
                or not isinstance(admission,dict) or admission.get('admission_digest')!=expected_admission_digest
                or canonical_hash({k:v for k,v in admission.items() if k!='admission_digest'})!=expected_admission_digest
                or admission.get('schema')!='van.account-restriction-admission/1'
                or admission.get('action')!='account_restrict' or admission.get('purpose')!='ACCOUNT_RESTRICTION_CONTROL'
                or admission.get('owner_id')!='owner' or admission.get('device_id')!=parent.intent.device_id
                or admission.get('operation_id')!=parent_operation_id or admission.get('native_request')!=original_request
                or parent.intent.authority_ref!=admission.get('authority_ref')+'::review:'+admission.get('native_review_digest')):
            raise AccountEffectConflict('Restriction original admission differs')
        if original_request['variant']=='RESTRICT':
            if any(admission[k] is not None for k in ('reauth_purpose','reauth_fact_id','reauth_fact_digest','reauth_proof_ref')):
                raise AccountEffectConflict('Restriction original narrowing admission differs')
        elif (admission['reauth_purpose']!='ACCOUNT_RESTRICTION_RECOVERY_REAUTH_DATA'
                or admission['reauth_fact_id']!=original_request['reauth_fact_id']
                or admission['reauth_fact_digest']!=original_request['reauth_fact_digest']
                or admission['reauth_proof_ref'] is None):
            raise AccountEffectConflict('Restriction original recovery admission differs')
        context=admission.get('context');alias=original_request.get('alias')
        self._restriction_child_request(child_request,parent_operation_id,alias)
        if (not isinstance(context,dict) or not isinstance(alias,str) or child_request.get('alias')!=alias
                or 'account:'+alias not in parent.intent.targets or context.get('alias')!=alias
                or context.get('original_device_id')!=parent.intent.device_id
                or context.get('resource_version')!=parent.intent.resource_version
                or context.get('variant')!=original_request.get('variant')
                or (original_request.get('variant')=='RESTRICT' and context.get('reason_code')!=original_request.get('reason_code'))
                or context.get('semantic_digest')!=canonical_hash({k:v for k,v in original_request.items() if k not in {'reauth_fact_id','reauth_fact_digest'}})
                or context.get('expected_revision')!=original_request.get('expected_revision',0)
                or context.get('expected_digest')!=original_request.get('expected_digest')
                or context.get('restriction_id')!=(original_request.get('restriction_id') or 'proposed:'+parent.intent.resource_version)
                or (original_request.get('variant')=='RECONCILE_DATA' and context.get('parent_operation_id')!=original_request.get('parent_operation_id'))
                or 'account-control-domain:'+str(context.get('account_control_domain')) not in parent.intent.targets
                or original_request.get('variant') not in {'RESTRICT','BEGIN_REAUTH','COMPLETE_REAUTH','RECONCILE_DATA'}
                or not isinstance(current_resource_version,str) or re.fullmatch(r'[0-9a-f]{64}',current_resource_version) is None
                or child_intent.resource_version!=current_resource_version):
            raise AccountEffectConflict('Restriction original scope differs')
        raw=registry._restrictions.get(alias)
        row=validate_record(raw) if raw is not None else None
        if row is not None and (row['alias']!=alias or row['reason_code']!=context['reason_code']
                or row['account_control_domain']!=context['account_control_domain'] or row['device_id']!=parent.intent.device_id):
            raise AccountEffectConflict('Restriction current row scope differs')
        rev=original_request.get('expected_revision',0);expected=original_request.get('expected_digest')
        if type(rev) is not int or rev<0:raise AccountEffectConflict('Restriction original revision differs')
        wanted_id=original_request.get('restriction_id') if rev else parent_operation_id
        matches=[] if row is None else [e for e in row['events'] if e['operation_id']==parent_operation_id]
        if matches:
            if original_request['variant']=='RECONCILE_DATA':
                raise AccountEffectConflict('Restriction metadata-only parent cannot have a transition')
            event=matches[0];index=row['events'].index(event)
            phase={'RESTRICT':'RESTRICTED','BEGIN_REAUTH':'REAUTH_PENDING','COMPLETE_REAUTH':'LINKED_READ_ONLY'}[original_request['variant']]
            if (len(matches)!=1 or row['restriction_id']!=wanted_id or row['incarnation']!=context.get('incarnation')
                    or row['account_control_domain']!=context['account_control_domain']
                    or row['device_id']!=parent.intent.device_id or index!=rev or event['to_phase']!=phase
                    or event['request_digest']!=parent.intent.request_digest or event['resource_version']!=parent.intent.resource_version
                    or event['admission_digest']!=expected_admission_digest or event['previous_digest']!=expected
                    or (rev==0 and row['origin']['review_digest']!=context['review_digest'])):
                raise AccountEffectConflict('Restriction original transition differs')
            outcome='TRANSITION_OBSERVED';event_ref=canonical_hash(event)
        else:
            if (current_resource_version!=parent.intent.resource_version or
                    (rev==0 and row is not None) or
                    (rev>0 and (row is None or row['restriction_id']!=wanted_id or row['incarnation']!=context.get('incarnation')
                               or row['revision']!=rev or canonical_hash(row)!=expected))):
                raise AccountEffectConflict('Restriction original preimage differs')
            outcome='CURRENT_PREIMAGE_OBSERVED';event_ref=None
        if (child_request.get('restriction_id')!=(row['restriction_id'] if row else parent_operation_id)
                or child_request.get('expected_revision')!=(row['revision'] if row else 0)
                or child_request.get('expected_digest')!=(canonical_hash(row) if row else None)):
            raise AccountEffectConflict('Restriction reconciliation current DATA differs')
        refs=self._restriction_bundle_refs(states,parent_operation_id,original_admission,related_admissions)
        for related in (original_admission,*related_admissions):
            if related['native_request']['variant']!='RECONCILE_DATA':continue
            c=related['context']
            if (c['resource_version']!=current_resource_version or c['expected_revision']!=(row['revision'] if row else 0)
                    or c['expected_digest']!=(canonical_hash(row) if row else None)
                    or c['restriction_id']!=(row['restriction_id'] if row else c['parent_operation_id'])):
                raise AccountEffectConflict('Restriction causal metadata preimage changed')
        if not isinstance(expected_operation_refs,(list,tuple)) or list(expected_operation_refs)!=refs:
            raise AccountEffectConflict('Restriction reviewed causal operations differ')
        all_admissions=[original_admission,*related_admissions]
        anchor_admission=next(a for a in all_admissions if a['native_request']['variant']!='RECONCILE_DATA')
        anchor_id=anchor_admission['operation_id'];anchor_state=states[anchor_id]
        anchor_req=anchor_admission['native_request'];anchor_context=anchor_admission['context']
        anchor_rev=anchor_req.get('expected_revision',0);anchor_expected=anchor_req.get('expected_digest')
        anchor_events=[] if row is None else [e for e in row['events'] if e['operation_id']==anchor_id]
        if anchor_events:
            anchor_event=anchor_events[0]
            anchor_phase={'RESTRICT':'RESTRICTED','BEGIN_REAUTH':'REAUTH_PENDING','COMPLETE_REAUTH':'LINKED_READ_ONLY'}[anchor_req['variant']]
            if (anchor_state.phase=='REFUSED' or len(anchor_events)!=1 or row['events'].index(anchor_event)!=anchor_rev or anchor_event['to_phase']!=anchor_phase
                    or anchor_event['request_digest']!=anchor_state.intent.request_digest
                    or anchor_event['resource_version']!=anchor_state.intent.resource_version
                    or anchor_event['admission_digest']!=anchor_admission['admission_digest']
                    or anchor_event['previous_digest']!=anchor_expected
                    or row['incarnation']!=anchor_context['incarnation']
                    or (anchor_rev==0 and row['origin']['review_digest']!=anchor_context['review_digest'])):
                raise AccountEffectConflict('Restriction causal anchor transition differs')
            anchor_outcome='TRANSITION_OBSERVED';anchor_ref=canonical_hash(anchor_event)
        else:
            if (anchor_state.phase=='APPLIED' or current_resource_version!=anchor_state.intent.resource_version
                    or (anchor_rev==0 and row is not None)
                    or (anchor_rev>0 and (row is None or row['restriction_id']!=anchor_req['restriction_id']
                        or row['incarnation']!=anchor_context['incarnation'] or row['revision']!=anchor_rev
                        or canonical_hash(row)!=anchor_expected))):
                raise AccountEffectConflict('Restriction causal anchor preimage differs')
            anchor_outcome='CURRENT_PREIMAGE_OBSERVED';anchor_ref=None
        summary={'outcome':outcome,'alias':alias,'restriction_id':row['restriction_id'] if row else None,
                 'incarnation':row['incarnation'] if row else None,'revision':row['revision'] if row else 0,
                 'record_digest':canonical_hash(row) if row else None,'event_ref':event_ref,
                 'admission_digest':expected_admission_digest,'resource_version':current_resource_version,
                 'resolved_operations':[ref['operation_id'] for ref in refs if states[ref['operation_id']].phase in {'IN_FLIGHT','UNKNOWN'}],
                 'selected_parent_operation_id':parent_operation_id,'anchor_operation_id':anchor_id,
                 'anchor_outcome':anchor_outcome,'anchor_event_ref':anchor_ref}
        evidence={'original_request':original_request,'original_admission':original_admission,'observed_row':row,
                  'related_admissions':list(related_admissions),'operation_refs':refs}
        return RestrictionResolutionQualification(parent_operation_id,parent.event_ref,canonical_hash(asdict(parent.intent)),
            canonical_hash(asdict(child_intent)),json.dumps(summary,sort_keys=True,separators=(',',':')),
            json.dumps(child_request,sort_keys=True,separators=(',',':')),
            json.dumps(evidence,sort_keys=True,separators=(',',':')))

    def claim_restriction_resolution(self, child_intent, qualification, *, now_unix=None):
        if type(qualification) is not RestrictionResolutionQualification or qualification.child_hash!=canonical_hash(asdict(child_intent)):
            raise AccountEffectConflict('Restriction reconciliation qualification differs')
        request=json.loads(qualification.child_request_json)
        self._restriction_child_request(request,qualification.parent_id,qualification.summary['alias'])
        if canonical_hash(request)!=child_intent.request_digest:
            raise AccountEffectConflict('Restriction reconciliation child binding differs')
        return self._claim(child_intent,now_unix=now_unix,restriction_parent=qualification)

    def append_restriction_resolution(self, child_claim, qualification, *, now_unix=None, before_append=None, clock=None):
        if type(qualification) is not RestrictionResolutionQualification or qualification.child_hash!=canonical_hash(asdict(child_claim.intent)):
            raise AccountEffectConflict('Restriction reconciliation qualification differs')
        now=int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            states=self._states();parent=states.get(qualification.parent_id);child=states.get(child_claim.intent.operation_id)
            if (parent is None or parent.event_ref!=qualification.parent_ref or canonical_hash(asdict(parent.intent))!=qualification.parent_hash
                    or child is None or child.intent!=child_claim.intent or child.phase not in {'IN_FLIGHT','UNKNOWN'}):
                raise AccountEffectConflict('Restriction reconciliation journal changed')
            summary=qualification.summary
            body={'schema':SCHEMA,'record_type':'RESTRICTION_RESOLUTION','parent_id':qualification.parent_id,
                  'parent_ref':parent.event_ref,'parent_hash':qualification.parent_hash,'child_id':child.intent.operation_id,
                  'child_ref':child.event_ref,'child_hash':qualification.child_hash,'child_request':json.loads(qualification.child_request_json),
                  'evidence':json.loads(qualification.evidence_json),
                  'summary':summary,'summary_hash':canonical_hash(summary),'authority_issued':False}
            event=make_event(EventKind.ACCOUNT_OPERATION,PRODUCER,body,event_time_ms=now*1000,received_time_ms=now*1000,
                             correlation_id=child.intent.operation_id)
            self._validate_restriction_record(event,states,self._restriction_resolutions())
            if before_append is not None:before_append()
            current=clock() if clock is not None else int(time.time())
            if type(current) is not int or current<now or current>=child.intent.expires_at_unix:
                raise AccountEffectAuthorityExpired('Restriction reconciliation authority expired before metadata append')
            self.ledger.append(event)
            return {'resolution_ref':event.hash,'resolution_child_operation_id':child.intent.operation_id,**summary}

    @staticmethod
    def _public_result(result):
        if not isinstance(result, dict):
            raise AccountEffectError("native outcome must be structured public metadata")
        def inspect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise AccountEffectError("native outcome keys must be text")
                    if re.search(r"token|password|signing.?key|client.?secret", key, re.I):
                        raise AccountEffectError("credential material needs a native vault reference, not journal storage")
                    inspect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    inspect(child)
        inspect(result)
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError):
            raise AccountEffectError("native outcome must contain finite JSON values") from None

    def _append(self, intent, phase, previous_ref, result=None, *, now):
        event = make_event(EventKind.ACCOUNT_OPERATION, PRODUCER,
            {"schema": SCHEMA, "intent": asdict(intent), "intent_hash": canonical_hash(asdict(intent)),
             "phase": phase, "previous_ref": previous_ref, "result": result},
            event_time_ms=now * 1000, received_time_ms=now * 1000,
            correlation_id=intent.operation_id)
        self.ledger.append(event)
        return AccountEffectState(intent, phase, event.hash, result)

    def _resolved_safety_obligation(self,state):
        if state.intent.command=='account_restrict':
            resolutions=self._restriction_resolutions()
            return any(state.intent.operation_id in p['summary']['resolved_operations'] or
                       p['child_id']==state.intent.operation_id for p in resolutions.values())
        if state.intent.command!='account_remove':return False
        from commander.account_cleanup import UnlinkRecoveryBook
        return UnlinkRecoveryBook(self.ledger,initialize=False,secrets_root=self.cleanup_secrets_root).resolved(state.intent.operation_id)

    def claim_cleanup(self,intent,qualified_parent,*,now_unix=None):
        from commander.account_cleanup import UnlinkRecoveryBook
        UnlinkRecoveryBook(self.ledger,initialize=False,secrets_root=self.cleanup_secrets_root).require_qualified(qualified_parent)
        return self._claim(intent,now_unix=now_unix,qualified_parent=qualified_parent)

    def claim(self,intent,*,now_unix=None):
        return self._claim(intent,now_unix=now_unix)

    def _claim(self, intent, *, now_unix=None,qualified_parent=None,restriction_parent=None):
        intent.validate()
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            states = self._states()
            previous = states.get(intent.operation_id)
            if previous is not None:
                if previous.intent != intent:
                    raise AccountEffectConflict("native operation conflicts with its original actor, request or resource")
                if previous.phase not in {"APPLIED", "REFUSED"}:
                    raise AccountEffectUnknown("native operation outcome is unconfirmed; never repeat its effect")
                return previous
            if now >= intent.expires_at_unix:
                raise AccountEffectAuthorityExpired("native operation authority expired before dispatch")
            related={}
            if restriction_parent is not None:
                evidence=json.loads(restriction_parent.evidence_json)
                if self._restriction_bundle_refs(states,restriction_parent.parent_id,evidence['original_admission'],evidence['related_admissions'])!=restriction_parent.operation_refs:
                    raise AccountEffectConflict('Restriction causal qualification changed')
                for ref in restriction_parent.operation_refs:
                    current=states.get(ref['operation_id'])
                    allowed={'IN_FLIGHT','UNKNOWN','APPLIED','REFUSED'} if ref['operation_id']==restriction_parent.summary['anchor_operation_id'] else {'IN_FLIGHT','UNKNOWN'}
                    if (current is None or current.phase not in allowed
                            or current.event_ref!=ref['event_ref'] or canonical_hash(asdict(current.intent))!=ref['intent_hash']):
                        raise AccountEffectConflict('Restriction causal operation changed')
                    related[ref['operation_id']]=ref
            for state in states.values():
                if state.phase in {"IN_FLIGHT", "UNKNOWN"} and targets_overlap(intent.targets,state.intent.targets):
                    if restriction_parent is not None and state.intent.operation_id in related:
                        if (intent.command!='account_restrict' or intent.device_id!=state.intent.device_id
                                or intent.targets!=state.intent.targets):raise AccountEffectConflict('Restriction reconciliation parent changed')
                        continue
                    if qualified_parent is not None and state.intent.operation_id==qualified_parent.operation_id:
                        from commander.account_cleanup import UnlinkRecoveryBook
                        UnlinkRecoveryBook(self.ledger,initialize=False,secrets_root=self.cleanup_secrets_root).require_qualified(qualified_parent)
                        if (intent.command!='account_remove' or intent.device_id!=qualified_parent.device_id
                                or intent.targets!=state.intent.targets):raise AccountEffectConflict("Cleanup child scope differs from original")
                        continue
                    if self._resolved_safety_obligation(state):continue
                    raise AccountEffectConflict("native target has an original effect requiring reconciliation")
            return self._append(intent, "IN_FLIGHT", "", now=now)

    def require_clear_targets(self, targets):
        with self.ledger.atomic():
            for state in self._states().values():
                if state.phase in {"IN_FLIGHT", "UNKNOWN"} and targets_overlap(targets,state.intent.targets):
                    if self._resolved_safety_obligation(state):continue
                    raise AccountEffectConflict("native target has an original effect requiring reconciliation")

    def refuse(self, claim, status_code, *, now_unix=None):
        """Only for a handler refusal BEFORE the first native effect marker."""
        if type(status_code) is not int or not 400 <= status_code < 500:
            raise AccountEffectError("native pre-effect refusal status is invalid")
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            current = self._states().get(claim.intent.operation_id)
            if current != claim or current.phase != "IN_FLIGHT":
                raise AccountEffectUnknown("native refusal does not match its original attempt")
            return self._append(claim.intent, "REFUSED", claim.event_ref,
                {"status_code": status_code, "detail": "Original request was refused before any account effect"}, now=now)

    def complete(self, claim, public_result, *, now_unix=None):
        self._public_result(public_result)
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            current = self._states().get(claim.intent.operation_id)
            if current is None or current.intent != claim.intent:
                raise AccountEffectUnknown("native operation claim is unavailable")
            if current.phase == "APPLIED" and current.result == public_result:
                return current
            if current.phase != "IN_FLIGHT" or current.event_ref != claim.event_ref:
                raise AccountEffectUnknown("native operation completion does not match its original attempt")
            return self._append(claim.intent, "APPLIED", claim.event_ref, public_result, now=now)

    def uncertain(self, claim, *, now_unix=None):
        now = int(time.time()) if now_unix is None else now_unix
        with self.ledger.atomic():
            current = self._states().get(claim.intent.operation_id)
            if current is None or current.intent != claim.intent:
                raise AccountEffectUnknown("native operation claim is unavailable")
            if current.phase in {"UNKNOWN", "APPLIED"}:
                return current
            if current.event_ref != claim.event_ref:
                raise AccountEffectUnknown("native operation attempt changed")
            return self._append(claim.intent, "UNKNOWN", claim.event_ref, now=now)

    def status(self, operation_id, device_id):
        with self.ledger.atomic():
            state = self._states().get(operation_id)
            if state is not None and state.intent.device_id != device_id:
                raise AccountEffectConflict("native operation belongs to another device")
            return state
