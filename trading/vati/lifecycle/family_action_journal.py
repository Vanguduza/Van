"""Durable family requests on the existing account ledger, never authority.

A plan is immutable across restart. Each transport request joins an original
leg target; observing a terminal partial fill never licenses resending it.
"""
from fractions import Fraction

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import committed_source_snapshot
from vati.lifecycle.family_actions import FamilyActionError, exact_decimal

VERSION = 'family-action-journal/1'
PRODUCER = 'vati-account-lifecycle'


def target_ref(action_ref, target):
    return canonical_hash({'family_action_ref': action_ref, 'original_target': target})


def quantity(body):
    return exact_decimal(Fraction(int(body['numerator']), int(body['denominator'])))


class FamilyActionJournal:
    def __init__(self, ledger):
        self.ledger = ledger

    def plans(self):
        for event in self.ledger.iter(EventKind.SESSION):
            p = event.payload
            if event.producer != PRODUCER or p.get('version') != VERSION:
                continue
            if (event.hash != canonical_hash(event.body()) or p.get('state') != 'PREPARED'
                    or p.get('plan_hash') != canonical_hash(p.get('plan'))
                    or event.correlation_id != p.get('family_id')):
                raise FamilyActionError('family action journal contains an invalid original plan')
            yield event

    def find(self, family_id, action_key):
        matches = [e for e in self.plans() if e.correlation_id == family_id
                   and e.payload.get('action_key') == action_key]
        if len(matches) > 1:
            raise FamilyActionError('family action key has conflicting original plans')
        return matches[0] if matches else None

    def prepare(self, plan, *, action_key, now_ms, request_hash=None, explicit_authority_ref=None):
        if not isinstance(action_key, str) or not action_key:
            raise FamilyActionError('original family action identity is required')
        with self.ledger.atomic():
            previous = self.find(plan.snapshot.family_id, action_key)
            if previous is not None:
                if (previous.payload.get('request_hash') != request_hash
                        or previous.payload.get('explicit_authority_ref') != explicit_authority_ref):
                    raise FamilyActionError('original family request/authority payload differs')
                if previous.payload['plan_hash'] != plan.digest:
                    raise FamilyActionError('original family action cannot be replanned from later quantities')
                return previous
            if explicit_authority_ref is not None and any(
                    e.payload.get('explicit_authority_ref') == explicit_authority_ref for e in self.plans()):
                raise FamilyActionError('exact explicit target authority already consumed')
            extras = {}
            if request_hash is not None:
                extras['request_hash'] = request_hash
            if explicit_authority_ref is not None:
                extras['explicit_authority_ref'] = explicit_authority_ref
            event = make_event(EventKind.SESSION, PRODUCER,
                {'version': VERSION, 'state': 'PREPARED', 'family_id': plan.snapshot.family_id,
                 'action_key': action_key, 'plan': plan.body(), 'plan_hash': plan.digest,
                 'execution_authority': False, **extras}, event_time_ms=now_ms,
                received_time_ms=now_ms, correlation_id=plan.snapshot.family_id)
            self.ledger.append(event)
        # Publication is a prerequisite to transport, including after ACK loss.
        with committed_source_snapshot(self.ledger):
            found = self.find(plan.snapshot.family_id, action_key)
            if found is None or found.hash != event.hash:
                raise FamilyActionError('family action plan is not committed before native effects')
        return event

    def target_attempt(self, action, target):
        ref = target_ref(action.hash, target)
        matches = [e for e in self.ledger.iter(EventKind.EXIT_ATTEMPT)
            if e.producer == 'vati-execution-router'
            and e.payload.get('state') == 'REQUESTED'
            and e.payload.get('family_action_ref') == action.hash
            and e.payload.get('family_target_ref') == ref]
        if len(matches) > 1:
            raise FamilyActionError('original family leg target was sent more than once')
        return matches[0] if matches else None

    def target_outcome(self, action, target):
        attempt = self.target_attempt(action, target)
        if attempt is None:
            return None, None
        outcomes = [e for e in self.ledger.iter(EventKind.EXIT_ATTEMPT)
            if e.producer == 'vati-execution-router' and e.payload.get('request_ref') == attempt.hash
            and e.hash == canonical_hash(e.body())]
        if not outcomes:
            return attempt, None
        return attempt, outcomes[-1]

    def progress(self, action):
        """Observed original effects only; unknown/teardown is never completion."""
        closed = Fraction(0); targets = []; unresolved = False
        original_legs={leg['position_id']:leg for leg in action.payload['plan']['snapshot']['legs']}
        aggregate_unknown=action.payload['plan']['requested_quantity'] is None
        if aggregate_unknown and action.payload['plan']['action']!='FULL_CLOSE':
            raise FamilyActionError('only original mandatory full protection can retain unknown aggregate quantity')
        unresolved=aggregate_unknown
        for target in action.payload['plan']['targets']:
            requested = Fraction(quantity(target['quantity']))
            attempt,outcome = self.target_outcome(action,target)
            actual = Fraction(0); state = 'UNEXECUTED'
            if requested == 0:
                state = 'NO_NATIVE_TARGET'
            elif attempt is not None:
                state = 'UNKNOWN' if outcome is None else outcome.payload['state']
                if outcome is not None and outcome.payload.get('dispatch_refusal_ref'):
                    refusal = next((e for e in self.ledger.iter(EventKind.SESSION)
                        if e.hash == outcome.payload['dispatch_refusal_ref']
                        and e.producer == 'vati-execution-router'
                        and e.hash == canonical_hash(e.body())
                        and e.payload.get('event') == 'FAMILY_DISPATCH_NOT_SENT'
                        and e.payload.get('exit_request_ref') == attempt.hash),None)
                    if refusal is None or state != 'NOT_EXECUTED' or outcome.payload.get('receipt_event_ref') is not None:
                        raise FamilyActionError('family target local refusal is not bound to its original request')
                elif outcome is not None:
                    receipt = next((e for e in self.ledger.iter(EventKind.EXECUTION_RECEIPT)
                        if e.hash == outcome.payload.get('receipt_event_ref')),None)
                    if (receipt is None or receipt.hash != canonical_hash(receipt.body())
                            or receipt.payload.get('exit_request_ref') != attempt.hash
                            or receipt.payload.get('broker_position_id') != target['position_id']):
                        raise FamilyActionError('family target outcome lacks its original bound receipt')
                    from vati.execution.base import ExecutionReceipt
                    from dataclasses import fields
                    body={f.name:receipt.payload.get(f.name) for f in fields(ExecutionReceipt) if f.name!='receipt_hash'}
                    if receipt.payload.get('receipt_hash') != canonical_hash(body):
                        raise FamilyActionError('family original execution receipt seal differs')
                    actual=Fraction(str(receipt.payload.get('filled_qty','0')))
                    if actual < 0 or actual > requested:
                        raise FamilyActionError('family native execution exceeds original target')
                unresolved = unresolved or state not in {'CONFIRMED','PARTIAL_CONFIRMED','NOT_EXECUTED'}
            else:
                unresolved = unresolved or requested > 0
            unknown_leg=aggregate_unknown and original_legs[target['position_id']]['remaining'] is None
            if unknown_leg:
                if attempt is not None or requested!=0:
                    raise FamilyActionError('unknown original target cannot issue a new transport request')
                state='ORIGINAL_NATIVE_QUANTITY_UNKNOWN';unresolved=True
            closed += actual
            targets.append({'position_id':target['position_id'],'trade_intent_id':target['trade_intent_id'],
                'target_ref':target_ref(action.hash,target),'request_ref':attempt.hash if attempt else None,
                'outcome_ref':outcome.hash if outcome else None,'state':state,
                'confirmed_quantity':str(exact_decimal(actual)),
                'unmet_quantity':None if unknown_leg else str(exact_decimal(requested-actual))})
        requested=None if aggregate_unknown else Fraction(quantity(action.payload['plan']['requested_quantity']))
        residual=None if requested is None else requested-closed
        return {'version':VERSION,'family_action_ref':action.hash,'family_id':action.correlation_id,
            'result_scope':'ORIGINAL_BOUND_FAMILY_ACTION',
            'family_revision':action.payload['plan']['snapshot']['family_revision'],
            'source_snapshot_ref':action.payload['plan']['snapshot_ref'],
            'policy_hash':action.payload['plan']['policy_hash'],
            'requested_quantity':None if requested is None else str(exact_decimal(requested)),
            'confirmed_quantity':str(exact_decimal(closed)), 'residual_quantity':None if residual is None else str(exact_decimal(residual)),
            'unresolved_native_effect':unresolved, 'state':'COMPLETE' if residual==0 and not unresolved else 'INCOMPLETE',
            'targets':targets,'execution_authority':False}
