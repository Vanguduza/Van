"""Original verified mandate evidence, never a fresh or enlarged grant.

The live authority owner must verify capture. Historical validation checks the
original signed statement and effective-policy hash without re-admitting it.
Missing legacy proof remains unbound; its financial history is not discarded.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.authority import OwnerAuthority, PREFIX, MAX_STANDING_LIFETIME_SECONDS, _unb64u, canonical_statement
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import committed_source_snapshot
from vati.core import EventKind
from vati.funding.native import native_int
from vati.risk.control_archive import archive_verified_control
from vati.risk.mandate import TradingMandate, _effective_policy, mandate_subject, trading_temperament_subject
from vati.risk.native_history import original_native_risk_input
from vati.risk.serde import _enc, mandate_binding_hash

SCHEMA='vati.original-mandate-source/1'
PROOF_SCHEMA='vati.original-standing-authority/1'


@dataclass(frozen=True,init=False)
class OriginalMandatePolicy:
    """Immutable historical policy data, deliberately outside TradingMandate."""
    _body_json: bytes

    def body(self):return json.loads(self._body_json)


def capture_mandate_source(mandate,raw,*,now_ms):
    """Capture through existing real authority, or explicit unavailable data."""
    try:
        native_int(now_ms,minimum=0)
        if type(mandate) is not TradingMandate or not mandate.authority_matches_policy():
            raise ValueError('effective mandate is not admitted')
        if mandate_subject(raw)!=mandate.owner_policy_subject:
            raise ValueError('raw mandate drifted from the admitted effective policy')
        bindings=getattr(mandate,'_verified_owner_key_bindings',())
        selected=[('mandate-admit',mandate_subject(mandate),'owner_signature_ref',mandate.owner_signature_ref)]
        if mandate.temperament_owner_signature_ref:
            selected.append(('trading-temperament-admit',trading_temperament_subject(raw),
                'temperament_owner_signature_ref',mandate.temperament_owner_signature_ref))
        if len(bindings)!=len(selected):raise ValueError('original standing key bindings unavailable')
        proofs=[]
        for binding,(act,subject,field,ref) in zip(bindings,selected):
            if binding is None or not binding.is_current():raise ValueError('standing owner key changed')
            token=raw[field]
            verified=binding._source.verify(token,act=act,subject=subject,now_unix=now_ms//1000,
                single_use=False,max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS)
            if verified.ref!=ref:raise ValueError('original standing authority changed')
            proof=archive_verified_control(token,verified);proof['schema']=PROOF_SCHEMA;proofs.append(proof)
        result={'schema':SCHEMA,'state':'ORIGINAL_BOUND','captured_at_ms':now_ms,
            'effective_policy':_enc(asdict(mandate)),'mandate_hash':mandate_binding_hash(mandate),
            'signed_input':json.loads(canonical_json(raw)),
            'authorities':proofs,'execution_authority':False,'current_policy_qualified':False}
        validate_mandate_source(result,decision_time_ms=now_ms)
        return result
    except Exception:
        # This metadata cannot override the live RiskAuthority result. Future
        # reservation admission must require its own complete original proof.
        return {'schema':SCHEMA,'state':'UNAVAILABLE','reason':'ORIGINAL_MANDATE_PROOF_UNAVAILABLE',
            'execution_authority':False,'current_policy_qualified':False}


def _original_authority(proof,*,act,subject,decision_time_ms):
    if (type(proof) is not dict or set(proof)!={'schema','token','public_key_pem',
            'public_key_sha256','verified_authority'} or proof['schema']!=PROOF_SCHEMA
            or type(proof['token']) is not str or len(proof['token'])>16384):
        raise ValueError('original standing proof format')
    prefix,encoded,signature=proof['token'].split('.')
    body=json.loads(_unb64u(encoded))
    if type(body) is not dict or set(body)!={'act','subject','iat','exp','nonce','kid'}:
        raise ValueError('original standing statement format')
    native_int(body['iat'],minimum=0);native_int(body['exp'],minimum=body['iat']+1)
    expected=OwnerAuthority(act,subject,body['iat'],body['exp'],body['nonce'],body['kid'])
    if (prefix!=PREFIX or body['act']!=act or body['subject']!=subject
            or type(body['nonce']) is not str or not body['nonce']
            or type(body['kid']) is not str or not body['kid']
            or canonical_json(proof['verified_authority'])!=canonical_json(asdict(expected))
            or body['exp']-body['iat']>MAX_STANDING_LIFETIME_SECONDS
            or decision_time_ms//1000+60<body['iat'] or decision_time_ms//1000>=body['exp']):
        raise ValueError('original standing statement scope or lifetime')
    key=serialization.load_pem_public_key(proof['public_key_pem'].encode())
    if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1):
        raise ValueError('original standing key must be P256')
    der=key.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest()!=proof['public_key_sha256']:
        raise ValueError('original standing key fingerprint mismatch')
    key.verify(_unb64u(signature),canonical_statement(act=act,subject=subject,
        issued_at_unix=body['iat'],expires_at_unix=body['exp'],nonce=body['nonce']).encode(),ec.ECDSA(hashes.SHA256()))
    return expected


def validate_mandate_source(source,*,decision_time_ms,expected_hash=None):
    """Validate only original bytes, signature and historical decision time."""
    native_int(decision_time_ms,minimum=0)
    fields={'schema','state','captured_at_ms','effective_policy','mandate_hash','signed_input','authorities',
        'execution_authority','current_policy_qualified'}
    if (type(source) is not dict or set(source)!=fields or source['schema']!=SCHEMA
            or source['state']!='ORIGINAL_BOUND' or source['execution_authority'] is not False
            or source['current_policy_qualified'] is not False):raise ValueError('original standing source format')
    native_int(source['captured_at_ms'],minimum=0,maximum=decision_time_ms)
    body=source['effective_policy']
    if type(body) is not dict or set(body)!=set(TradingMandate.__dataclass_fields__):
        raise ValueError('original complete effective policy required')
    if (canonical_hash(body)!=source['mandate_hash']
            or expected_hash is not None and source['mandate_hash']!=expected_hash):
        raise ValueError('original effective policy does not match risk decision')
    policy=_effective_policy({k:v for k,v in body.items() if k!='owner_policy_subject'})
    subject=mandate_subject(policy);proofs=source['authorities']
    raw=source['signed_input']
    if type(raw) is not dict or mandate_subject(raw)!=subject:
        raise ValueError('original signed input does not match effective policy')
    count=2 if body['temperament_owner_signature_ref'] else 1
    if type(proofs) is not list or len(proofs)!=count:raise ValueError('original standing authority count')
    verified=_original_authority(proofs[0],act='mandate-admit',subject=subject,decision_time_ms=decision_time_ms)
    if proofs[0]['token']!=raw['owner_signature_ref']:
        raise ValueError('original standing token differs from signed input')
    profile_ref=''
    if count==2:
        profile=_original_authority(proofs[1],act='trading-temperament-admit',
            subject=trading_temperament_subject(raw),decision_time_ms=decision_time_ms)
        if proofs[1]['token']!=raw['temperament_owner_signature_ref']:
            raise ValueError('original temperament token differs from signed input')
        profile_ref=profile.ref
    restored=replace(policy,owner_signature_ref=verified.ref,temperament_owner_signature_ref=profile_ref)
    expected=_enc(asdict(restored));expected['owner_policy_subject']=subject
    if (canonical_json(expected)!=canonical_json(body)
            or not restored.signed_at_unix<=decision_time_ms//1000<restored.expires_at_unix):
        raise ValueError('original policy identity or decision lifetime mismatch')
    value=object.__new__(OriginalMandatePolicy)
    object.__setattr__(value,'_body_json',canonical_json(expected).encode())
    return value


def original_native_risk_mandate(ledger,event_ref,*,available_at_ms):
    """Original policy readback never resolves or drops legacy account losses."""
    with committed_source_snapshot(ledger):
        original=original_native_risk_input(ledger,event_ref,available_at_ms=available_at_ms)
        event=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.hash==event_ref)
        source=event.payload['inputs'].get('original_mandate_source')
        result={'schema':'vati.original-native-risk-mandate/1','source_event_ref':event_ref,
            'physical_account_key':original.context.physical_account_key,
            'monetary_scope_hash':original.context.monetary_scope_hash,'origin_alias':original.context.account_alias,
            'state':'UNBOUND','reason':'ORIGINAL_MANDATE_PROOF_UNAVAILABLE',
            'effective_policy':None,'execution_authority':False,'current_policy_qualified':False}
        if source is None:return result
        try:
            policy=validate_mandate_source(source,decision_time_ms=min(event.event_time_ms,event.received_time_ms),
                expected_hash=event.payload['decision']['mandate_hash']).body()
            if policy['account_alias']!=original.context.account_alias or policy['venue']!=event.payload['inputs']['intent']['venue']:
                raise ValueError('original standing policy account mismatch')
            result.update(state='ORIGINAL_BOUND',reason='',effective_policy=source['effective_policy'],
                mandate_hash=source['mandate_hash'],source_proof_hash=canonical_hash(source))
        except Exception:result['reason']='ORIGINAL_MANDATE_PROOF_INVALID_OR_UNAVAILABLE'
        return result
