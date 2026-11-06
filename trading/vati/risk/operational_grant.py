"""Scoped lifecycle policy admission on the existing account/authority owners.

VAN-SO-039 / VAN-EL-006 source implementation. These records issue neither
qualification nor owner signatures. Empty independent issuer configuration is
NOT_QUALIFIED. They cannot enlarge strategy, ADD, mandate or provider authority.
"""
from contextlib import contextmanager
from decimal import Decimal
from fractions import Fraction
import json

from vati.authority import MAX_STANDING_LIFETIME_SECONDS, OwnerAuthorityVerifier
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import EventKind, make_event
from vati.lifecycle.family_actions import FamilyActionError, amount, number
from vati.lifecycle.family_action_journal import quantity

VERSION = 'lifecycle-operational-grant/1'
PRODUCER = 'vati-lifecycle-policy-admission'
REQUIRED_GATES = frozenset({'conformance', 'native_close_constraints', 'authority',
    'risk_regression', 'replay', 'restart', 'unknown_effect', 'revocation'})
SCOPE_KEYS = frozenset({'environment','account_alias','venue','native_cohort','strategy_id',
                       'strategy_version','native_contract_refs','native_capability_refs'})
GRANT_KEYS = frozenset({'grant_id','policy_id','policy_version','policy_hash','scope',
    'operations','max_requested_quantity','max_family_risk_pct','qualification_hash',
    'source_hash','evidence_refs','activated_ms','expires_ms','parent_migration',
    'lease_epoch','fence_ref','issuer_key_id','owner_key_id'})
QUAL_KEYS = frozenset({'policy_id','policy_version','policy_hash','scope','source_hash',
    'evidence_refs','gates','issued_ms','expires_ms','issuer_key_id','evidence_domain',
    'operations','max_requested_quantity','max_family_risk_pct'})


class PolicyAdmissionError(FamilyActionError):
    pass


def qualification_reader(path):
    """Separate configured issuer trust; never default to the owner key set."""
    if not path:
        return None
    try:
        reader=OwnerAuthorityVerifier(registry_path=path)
        return reader if reader.keys else None
    except (OSError,ValueError,TypeError):
        return None


def sealed_copy(body):
    # Canonical immutable data, not a live caller mapping or truthy flag.
    return json.loads(canonical_json(body))


def subject(body):
    return VERSION + ':' + canonical_hash(body)


def _integer(value):
    return type(value) is int and value >= 0


def _scope(scope):
    if (type(scope) is not dict or set(scope) != SCOPE_KEYS
            or scope['environment'] not in {'PAPER','DEMO','LIVE'}
            or any(type(scope[k]) is not str or not scope[k] for k in
                   SCOPE_KEYS-{'native_contract_refs','native_capability_refs'})
            or any(type(scope[k]) is not list or not scope[k]
                   or any(type(v) is not str or not v for v in scope[k])
                   or len(set(scope[k])) != len(scope[k])
                   for k in ('native_contract_refs','native_capability_refs'))):
        raise PolicyAdmissionError('exact lifecycle policy/native scope is required')


class OperationalOptimizationGrants:
    """Ledger projection; independent qualification and owner intent stay separate."""
    def __init__(self, ledger, *, owner_authority, qualification_authority=None, clock):
        self.ledger = ledger
        self.owner = owner_authority
        self.qualifier = qualification_authority
        self.clock = clock

    def _verify_qualification(self, grant, qualification, signature, now_ms):
        if self.qualifier is None:
            raise PolicyAdmissionError('NOT_QUALIFIED: independent lifecycle policy issuer is unavailable')
        if type(qualification) is not dict or set(qualification) != QUAL_KEYS:
            raise PolicyAdmissionError('independent lifecycle qualification schema is invalid')
        _scope(qualification['scope'])
        if (qualification['issuer_key_id'] != grant['issuer_key_id']
                or qualification['issuer_key_id'] == grant['owner_key_id']
                or qualification['evidence_domain'] not in {'SOURCE','NATIVE'}
                or (qualification['evidence_domain'] == 'SOURCE' and grant['scope']['environment'] != 'PAPER')
                or set(qualification['gates']) != REQUIRED_GATES
                or any(v is not True for v in qualification['gates'].values())
                or not _integer(qualification['issued_ms']) or not _integer(qualification['expires_ms'])
                or not qualification['issued_ms'] <= now_ms < qualification['expires_ms']
                or qualification['expires_ms'] < grant['expires_ms']
                or qualification['issued_ms'] > grant['activated_ms']
                or type(qualification['operations']) is not list
                or not set(grant['operations']) <= set(qualification['operations'])
                or amount(quantity(grant['max_requested_quantity']))>amount(quantity(qualification['max_requested_quantity']))
                or amount(quantity(grant['max_family_risk_pct']))>amount(quantity(qualification['max_family_risk_pct']))):
            raise PolicyAdmissionError('independent lifecycle qualification scope/validity/gates are not satisfied')
        for key in ('policy_id','policy_version','policy_hash','scope','source_hash','evidence_refs'):
            if qualification[key] != grant[key]:
                raise PolicyAdmissionError('independent qualification does not cover exact lifecycle grant')
        if canonical_hash(qualification) != grant['qualification_hash']:
            raise PolicyAdmissionError('independent qualification identity differs')
        verified = self.qualifier.verify(signature,act='lifecycle-policy-qualify',
            subject=subject(qualification),now_unix=now_ms//1000,single_use=False,
            max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS)
        if verified.key_id != qualification['issuer_key_id']:
            raise PolicyAdmissionError('independent qualification issuer differs from registered verifier')
        return verified

    def _validate(self, grant, qualification, owner_signature, qualification_signature, now_ms):
        if type(grant) is not dict or set(grant) != GRANT_KEYS:
            raise PolicyAdmissionError('lifecycle grant requires the exact versioned schema')
        _scope(grant['scope'])
        if (any(type(grant[k]) is not str or not grant[k] for k in
                ('grant_id','policy_id','policy_version','policy_hash','qualification_hash',
                 'source_hash','fence_ref','issuer_key_id','owner_key_id'))
                or grant['policy_version'] not in {'PROPORTIONAL_FLOOR_V1','EXPLICIT_LEGS_V1'}
                or type(grant['operations']) is not list or not grant['operations']
                or len(set(grant['operations'])) != len(grant['operations'])
                or not set(grant['operations']) <= {'PARTIAL_CLOSE','FULL_CLOSE','TIGHTEN_STOP'}
                or not _integer(grant['activated_ms']) or not _integer(grant['expires_ms'])
                or not grant['activated_ms'] <= now_ms < grant['expires_ms']
                or type(grant['evidence_refs']) is not list or not grant['evidence_refs']
                or any(type(v) is not str or not v for v in grant['evidence_refs'])
                or type(grant['lease_epoch']) is not int or grant['lease_epoch'] < 0
                or type(grant['parent_migration']) is not dict
                or set(grant['parent_migration']) != {'mode','original_family_revisions'}
                or grant['parent_migration']['mode'] not in {'NEW_ONLY','EXPLICIT_ORIGINAL_PARENTS'}
                or type(grant['parent_migration']['original_family_revisions']) is not list
                or any(type(v) is not str or not v for v in grant['parent_migration']['original_family_revisions'])
                or (grant['parent_migration']['mode']=='EXPLICIT_ORIGINAL_PARENTS'
                    and not grant['parent_migration']['original_family_revisions'])
                or (grant['parent_migration']['mode']=='NEW_ONLY'
                    and grant['parent_migration']['original_family_revisions'])):
            raise PolicyAdmissionError('lifecycle grant policy/bounds/activation/parent scope is invalid')
        for key in ('max_requested_quantity','max_family_risk_pct'):
            if quantity(grant[key]) <= 0:
                raise PolicyAdmissionError('lifecycle grant numeric bound must be exact and positive')
        independent = self._verify_qualification(grant,qualification,qualification_signature,now_ms)
        verified = self.owner.verify(owner_signature,act='lifecycle-policy-grant',subject=subject(grant),
            now_unix=now_ms//1000,single_use=False,max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS)
        if (verified.key_id != grant['owner_key_id'] or independent.key_id == verified.key_id
                or independent._verified_key_binding.public_key_sha256
                    == verified._verified_key_binding.public_key_sha256):
            raise PolicyAdmissionError('lifecycle owner and independent issuer identities must be distinct')
        if grant['activated_ms'] < verified.issued_at_unix*1000:
            raise PolicyAdmissionError('lifecycle activation barrier precedes its actual signed authorization')
        if verified.expires_at_unix*1000 < grant['expires_ms']:
            raise PolicyAdmissionError('lifecycle grant outlives original signed owner authority')
        return verified,independent

    def events(self, grant_id=None):
        for e in self.ledger.iter(EventKind.SESSION,correlation_id=grant_id):
            p=e.payload
            if e.producer != PRODUCER or p.get('version') != VERSION:
                continue
            if (e.hash != canonical_hash(e.body()) or e.correlation_id != p.get('grant_id')
                    or p.get('state') not in {'ADMITTED','REVOKED'}):
                raise PolicyAdmissionError('lifecycle grant journal integrity is unavailable')
            yield e

    def latest(self, grant_id):
        previous=None
        for e in self.events(grant_id):
            if (e.payload.get('previous_ref') != (previous.hash if previous else None)
                    or e.payload.get('revision') != (previous.payload['revision']+1 if previous else 1)):
                raise PolicyAdmissionError('lifecycle grant journal fork/revision mismatch')
            previous=e
        return previous

    def admit(self, grant, qualification, *, owner_signature, qualification_signature, expected_ref=None):
        grant,qualification=sealed_copy(grant),sealed_copy(qualification)
        with self.ledger.atomic():
            now=self.clock()
            previous=self.latest(grant.get('grant_id')) if type(grant) is dict and grant.get('grant_id') else None
            if previous is not None and previous.payload.get('grant_hash') == canonical_hash(grant):
                if previous.payload['state'] != 'ADMITTED':
                    raise PolicyAdmissionError('revoked original grant cannot be readmitted')
                if (previous.payload['owner_signature'] != owner_signature
                        or previous.payload['qualification_signature'] != qualification_signature
                        or previous.payload['qualification'] != qualification):
                    raise PolicyAdmissionError('original grant replay differs from its original authority')
                # Original readback is not new admission, even after expiry.
                return previous
            verified,independent=self._validate(grant,qualification,owner_signature,qualification_signature,now)
            if (previous.hash if previous else None) != expected_ref:
                raise PolicyAdmissionError('lifecycle grant compare-and-swap refused stale revision')
            if any(e.payload.get('owner_authority_ref') == verified.ref for e in self.events()):
                raise PolicyAdmissionError('owner lifecycle grant authority already consumed')
            event=make_event(EventKind.SESSION,PRODUCER,dict(version=VERSION,state='ADMITTED',
                grant_id=grant['grant_id'],grant=grant,grant_hash=canonical_hash(grant),
                qualification=qualification,qualification_signature=qualification_signature,
                owner_signature=owner_signature,owner_authority_ref=verified.ref,
                independent_authority_ref=independent.ref,previous_ref=expected_ref,
                revision=previous.payload['revision']+1 if previous else 1),
                event_time_ms=now,received_time_ms=now,correlation_id=grant['grant_id'])
            self.ledger.append(event)
        original=self.latest(grant['grant_id'])
        if original is None or original.hash != event.hash:
            raise PolicyAdmissionError('lifecycle grant authoritative readback failed')
        return event

    def revoke(self, grant_id, *, expected_ref, owner_signature):
        with self.ledger.atomic():
            now=self.clock();previous=self.latest(grant_id)
            body=dict(grant_id=grant_id,expected_ref=expected_ref)
            verified=self.owner.verify(owner_signature,act='lifecycle-policy-revoke',
                subject=subject(body),now_unix=now//1000,single_use=False)
            if (previous is None or previous.hash != expected_ref
                    or previous.payload['state'] != 'ADMITTED'):
                raise PolicyAdmissionError('lifecycle revocation compare-and-swap refused stale revision')
            if verified.key_id != previous.payload['grant']['owner_key_id']:
                raise PolicyAdmissionError('revocation owner differs from original lifecycle grant')
            if any(e.payload.get('owner_authority_ref') == verified.ref for e in self.events()):
                raise PolicyAdmissionError('owner lifecycle revocation authority already consumed')
            event=make_event(EventKind.SESSION,PRODUCER,dict(version=VERSION,state='REVOKED',
                grant_id=grant_id,grant_hash=previous.payload['grant_hash'],previous_ref=previous.hash,
                revision=previous.payload['revision']+1,owner_authority_ref=verified.ref),
                event_time_ms=now,received_time_ms=now,correlation_id=grant_id)
            self.ledger.append(event)
        return event

    def current(self, grant_id, *, expected_ref):
        event=self.latest(grant_id)
        if event is None or event.hash != expected_ref or event.payload['state'] != 'ADMITTED':
            raise PolicyAdmissionError('lifecycle grant is absent, revoked or replaced')
        p=event.payload
        self._validate(p['grant'],p['qualification'],p['owner_signature'],p['qualification_signature'],self.clock())
        return event

    @contextmanager
    def effect_guard(self, grant_id, *, expected_ref, lease_epoch, fence_ref, lease_fence):
        """Serialize fresh eligibility with revocation; caller first commits request.

        Existing durable request remains unresolved on any transport/commit loss.
        This guard is for new effects, never re-admission of historical receipts.
        """
        with self.ledger.atomic():
            current=self.current(grant_id,expected_ref=expected_ref)
            grant=current.payload['grant']
            if (grant['lease_epoch'] != lease_epoch or grant['fence_ref'] != fence_ref
                    or not callable(lease_fence) or lease_fence(lease_epoch) is not True):
                raise PolicyAdmissionError('current lifecycle grant lease/fence refused effect')
            # A lease reader can advance time/revoke a signer; resample afterward.
            self.current(grant_id,expected_ref=expected_ref)
            yield current

    def authorize_plan(self, event, plan, *, history, mandate, authority, adapter,
                       lease_epoch, fence_ref, explicit_signature=None, family_action=None, active_target=None):
        """Join real current owners; a planner flag/reference cannot admit effects."""
        from vati.risk.mandate import TradingMandate
        from vati.risk.authority import RiskAuthority, _canonical_hash
        from vati.risk.serde import mandate_binding_hash
        from vati.risk.mandate_source import validate_mandate_source
        from vati.execution.paper import PaperAdapter
        from vati.lifecycle.family_actions import EXPLICIT_LEGS_V1, policy_implementation_hash
        now=self.clock()
        event=self.current(event.payload['grant_id'],expected_ref=event.hash)
        grant=event.payload['grant'];scope=grant['scope'];binding=dict(plan.authority_refs)
        owner_verified=self.owner.verify(event.payload['owner_signature'],act='lifecycle-policy-grant',
            subject=subject(grant),now_unix=now//1000,single_use=False,
            max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS)
        mandate_keys=getattr(mandate,'_verified_owner_key_bindings',())
        if (not mandate_keys or mandate_keys[0] is None
                or mandate_keys[0].public_key_sha256 != owner_verified._verified_key_binding.public_key_sha256
                or not mandate_keys[0].is_current()):
            raise PolicyAdmissionError('lifecycle grant owner is not the current mandate owner')
        if (type(mandate) is not TradingMandate or not isinstance(authority,RiskAuthority)
                or not mandate.authority_matches_policy() or not mandate.owner_keys_current()
                or not mandate.signed_at_unix*1000 <= now < mandate.expires_at_unix*1000
                or mandate_binding_hash(authority.mandate) != mandate_binding_hash(mandate)
                or plan.policy.mode != 'ADMITTED' or plan.policy.qualification_ref != grant['qualification_hash']
                or plan.policy.policy_id != grant['policy_id'] or plan.policy.version != grant['policy_version']
                or plan.policy.artifact_hash != grant['policy_hash']
                or plan.policy.implementation_hash != grant['source_hash']
                or policy_implementation_hash() != grant['source_hash']
                or binding['grant_ref'] != event.hash or binding['current_mandate_ref'] != mandate_binding_hash(mandate)
                or binding['fence_ref'] != fence_ref or binding['lease_ref'] != str(lease_epoch)
                or plan.snapshot.account_alias != scope['account_alias']
                or adapter.account_alias != scope['account_alias'] or mandate.account_alias != scope['account_alias']
                or plan.snapshot.venue != scope['venue'] or adapter.venue != scope['venue']
                or mandate.venue != scope['venue'] or plan.action not in grant['operations']
                or plan.requested_quantity is None or plan.requested_quantity > quantity(grant['max_requested_quantity'])
                or not plan.snapshot.known):
            raise PolicyAdmissionError('lifecycle plan lacks exact current policy/mandate/risk/native authority')
        if scope['environment']=='PAPER' and type(adapter) is not PaperAdapter:
            raise PolicyAdmissionError('SOURCE paper qualification cannot authorize another native provider')
        refs=set();caps=set();risk_after=Fraction(0);other_full_unresolved=False
        native_positions={p.position_id:p for p in adapter.positions()}
        native_account=adapter.sync_account()
        for leg in plan.snapshot.legs:
            if leg.remaining == 0:
                continue
            command=history.commands.get(leg.trade_intent_id)
            if (command is None or command[0].get('strategy_id') != scope['strategy_id']
                    or command[0].get('strategy_version') != scope['strategy_version']
                    or leg.close_rules is None):
                raise PolicyAdmissionError('original native command/cohort differs from lifecycle grant')
            refs.add(leg.close_rules.contract_ref);caps.add(leg.close_rules.evidence_ref)
            completed=False;attempted=False
            target=next(t for t in plan.targets if t.position_id==leg.position_id)
            if family_action is not None:
                from vati.lifecycle.family_action_journal import FamilyActionJournal
                journal=FamilyActionJournal(self.ledger)
                observed=next((e for e in journal.plans() if e.hash==family_action.hash),None)
                if observed is None or observed.payload['plan_hash']!=plan.digest:
                    raise PolicyAdmissionError('family effect does not bind its original durable action')
                target_body=target.body()
                progress=journal.progress(observed)
                settled=next(t for t in progress['targets'] if t['position_id']==leg.position_id)
                attempted=settled['request_ref'] is not None
                completed=(settled['state'] in {'CONFIRMED','PARTIAL_CONFIRMED'}
                    and amount(target.quantity)==amount(Decimal(settled['confirmed_quantity'])))
                unknown=[t for t in progress['targets'] if t['state'] in {'UNKNOWN','ACCEPTED'}
                    and not (active_target is not None and t['position_id']==active_target.position_id
                             and t['outcome_ref'] is None)]
                if unknown and plan.action!='FULL_CLOSE':
                    raise PolicyAdmissionError('original family native effect remains unresolved')
                if (plan.action=='FULL_CLOSE' and active_target is not None
                        and settled['position_id']!=active_target.position_id
                        and settled['state'] in {'UNKNOWN','ACCEPTED'}):
                    # This is the original full target for another leg, not a
                    # fresh allocation. Its uncertainty cannot cancel lawful
                    # independent closure of the current original leg.
                    other_full_unresolved=True
                    continue
                if completed and leg.position_id not in native_positions:
                    continue
            capture=getattr(adapter,'close_capability_capture',lambda _pid:None)(leg.position_id)
            if (not isinstance(capture,dict)
                    or capture.get('evidence_ref')!=canonical_hash({k:v for k,v in capture.items() if k!='evidence_ref'})
                    or capture.get('contract_ref')!=canonical_hash(capture.get('contract'))
                    or capture.get('scope')!=dict(account_alias=scope['account_alias'],venue=scope['venue'],
                        position_id=leg.position_id,symbol=plan.snapshot.symbol,trade_intent_id=leg.trade_intent_id)
                    or capture.get('schema') != scope['native_cohort']
                    or capture.get('environment',capture.get('contract',{}).get('environment')) != scope['environment']
                    or capture.get('contract_ref') != leg.close_rules.contract_ref
                    or capture.get('evidence_ref') != leg.close_rules.evidence_ref
                    or (scope['environment']!='PAPER' and capture.get('provider_qualified') is not True)):
                raise PolicyAdmissionError('current actual native capability revision differs from original lifecycle plan')
            position=native_positions.get(leg.position_id)
            risk_contract=capture.get('risk',{})
            if (position is None or history.position_command(position) is None
                    or position.trade_intent_id!=leg.trade_intent_id):
                raise PolicyAdmissionError('current native position is not the original family leg')
            is_current=active_target is not None and active_target.position_id==leg.position_id
            reduction=amount(target.quantity) if not completed and (not attempted or is_current) else Fraction(0)
            remaining=amount(position.quantity)
            if reduction>remaining:
                raise PolicyAdmissionError('current native quantity is below original exact target')
            if target.action=='FULL_CLOSE' and reduction==remaining:
                if capture.get('full_close_allowed') is not True:
                    raise PolicyAdmissionError('actual native full-close capability is unavailable')
                continue
            if (position.stop_price is None
                    or risk_contract.get('loss_model')!='STOP_DISTANCE'
                    or risk_contract.get('account_currency')!=native_account.currency):
                raise PolicyAdmissionError('current native risk contract/protection is not qualified for partial allocation')
            value=Decimal(str(risk_contract.get('value_per_price_unit_per_lot')))
            if not value.is_finite() or value<=0:
                raise PolicyAdmissionError('current native risk valuation is unavailable')
            distance=(Fraction(position.entry_price)-Fraction(position.stop_price)
                if plan.snapshot.direction=='LONG' else Fraction(position.stop_price)-Fraction(position.entry_price))
            risk_after+=(remaining-reduction)*max(Fraction(0),distance)*Fraction(value)
        if active_target is not None:
            position=next((p for p in adapter.positions() if p.position_id==active_target.position_id),None)
            if (position is None or history.position_command(position) is None
                    or position.trade_intent_id!=active_target.trade_intent_id
                    or amount(position.quantity)<amount(active_target.quantity)
                    or (active_target.action=='FULL_CLOSE' and amount(position.quantity)!=amount(active_target.quantity))):
                raise PolicyAdmissionError('current original native leg cannot carry its exact bound target')
        if refs != set(scope['native_contract_refs']) or caps != set(scope['native_capability_refs']):
            raise PolicyAdmissionError('lifecycle grant native contract/capability set differs')
        original=next((e for e in history.rows if e.hash == binding['original_mandate_ref']
            and e.kind is EventKind.RISK_DECISION and e.producer in {'vati-account-coordinator','vati-account-service','vati-cycle','vati-account-lifecycle'}),None)
        if original is None:
            raise PolicyAdmissionError('original family mandate source is not bound')
        intent=original.payload.get('inputs',{}).get('intent',{})
        if (intent.get('account_alias') != scope['account_alias'] or intent.get('venue') != scope['venue']
                or intent.get('strategy_id') != scope['strategy_id']
                or intent.get('strategy_version') != scope['strategy_version']
                or intent.get('trade_intent_id') not in {leg.trade_intent_id for leg in plan.snapshot.legs}
                or not any(history.commands[leg.trade_intent_id][0].get('decision_hash') == original.payload.get('decision',{}).get('decision_hash')
                    for leg in plan.snapshot.legs if leg.trade_intent_id == intent.get('trade_intent_id'))):
            raise PolicyAdmissionError('original family mandate/command identity differs')
        original_decision=original.payload.get('decision',{})
        if (original_decision.get('decision_hash') != _canonical_hash({k:v for k,v in original_decision.items() if k!='decision_hash'})
                or original_decision.get('intent_hash') != canonical_hash(intent)
                or original_decision.get('trade_intent_id') != intent.get('trade_intent_id')
                or original_decision.get('decision') not in {'APPROVED','REDUCED'}):
            raise PolicyAdmissionError('original family risk approval is not sealed to its exact intent')
        equity=native_account.equity
        if not equity.is_finite() or equity<=0:
            raise PolicyAdmissionError('current native account equity is unavailable')
        maximum=min(amount(quantity(grant['max_family_risk_pct'])),
                    amount(Decimal(str(original_decision['approved_risk_pct']))),
                    amount(mandate.max_risk_per_trade))
        if other_full_unresolved and (plan.action!='FULL_CLOSE' or active_target is None or active_target.action!='FULL_CLOSE'):
            raise PolicyAdmissionError('unresolved native family risk cannot authorize allocation')
        if not other_full_unresolved and risk_after>maximum*Fraction(equity):
            raise PolicyAdmissionError('post-action native family risk exceeds original/current authority bounds')
        validate_mandate_source(original.payload['inputs'].get('original_mandate_source'),
            decision_time_ms=original.event_time_ms,expected_hash=original.payload['decision']['mandate_hash'])
        migration=grant['parent_migration']
        revision=next((e for e in history.rows if e.hash==plan.snapshot.family_revision
            and e.kind is EventKind.POSITION_FAMILY and e.producer=='vati-position-family'
            and e.correlation_id==plan.snapshot.family_id and e.hash==canonical_hash(e.body())),None)
        migrated=False
        if revision is not None:
            for ancestor in history.rows:
                if (ancestor.hash in migration['original_family_revisions']
                        and ancestor.kind is EventKind.POSITION_FAMILY and ancestor.producer=='vati-position-family'
                        and ancestor.correlation_id==plan.snapshot.family_id
                        and ancestor.hash==canonical_hash(ancestor.body())
                        and ancestor.received_time_ms<=grant['activated_ms']
                        and ancestor.payload.get('account_alias')==scope['account_alias']
                        and ancestor.payload.get('symbol')==plan.snapshot.symbol
                        and ancestor.payload.get('direction')==plan.snapshot.direction
                        and revision.payload.get('members',[])[:len(ancestor.payload.get('members',[]))]
                            ==ancestor.payload.get('members',[]) and ancestor.payload.get('members')):
                    migrated=True
        if (revision is None or (migration['mode']=='NEW_ONLY' and any(
                history.commands[leg.trade_intent_id][1] < grant['activated_ms'] for leg in plan.snapshot.legs))
                or (migration['mode']=='EXPLICIT_ORIGINAL_PARENTS' and not migrated)):
            raise PolicyAdmissionError('original family has no authorized policy migration')
        if plan.policy.version == EXPLICIT_LEGS_V1:
            verified=self.owner.verify(explicit_signature,act='lifecycle-explicit-targets',
                subject=subject({'grant_ref':event.hash,'plan_hash':plan.digest}),
                now_unix=now//1000,single_use=False)
            if verified.key_id != grant['owner_key_id']:
                raise PolicyAdmissionError('exact explicit target signer differs from original lifecycle owner')
            return verified.ref
        if explicit_signature is not None:
            raise PolicyAdmissionError('automatic policy does not consume an explicit target authority')
        return None
