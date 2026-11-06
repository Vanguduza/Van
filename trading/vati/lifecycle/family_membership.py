"""Original ledger membership joined to current native-owner observations.

This projection has no sender or authority. Missing positions remain unknown
unless original, request-bound close receipts account for their full quantity.
"""
from decimal import Decimal
from fractions import Fraction

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.exit_journal import VERSION as EXIT_VERSION
from vati.lifecycle.family import FamilyRegistry
from vati.lifecycle.family_actions import (
    FamilyActionError, FamilyLeg, FamilySnapshot, NativeCloseRules, exact_decimal,
)


def _close_rules(adapter, position):
    capture_fn = getattr(adapter, 'close_capability_capture', None)
    if not callable(capture_fn):
        return None
    capture = capture_fn(position.position_id)
    if not isinstance(capture, dict):
        return None
    body = {k: v for k, v in capture.items() if k != 'evidence_ref'}
    scope = capture.get('scope', {})
    contract = capture.get('contract', {})
    if (capture.get('evidence_ref') != canonical_hash(body)
            or capture.get('contract_ref') != canonical_hash(contract)
            or scope != dict(account_alias=adapter.account_alias, venue=adapter.venue,
                             position_id=position.position_id, symbol=position.symbol,
                             trade_intent_id=position.trade_intent_id)):
        raise FamilyActionError('native close capability is not bound to its actual original position')
    def decimal(name, default=None):
        value = contract.get(name, default)
        return None if value is None else Decimal(str(value))
    return NativeCloseRules(capture['evidence_ref'], capture['contract_ref'],
        decimal('quantity_quantum'), capture.get('partial_allowed') is True,
        capture.get('full_close_allowed') is True, decimal('partial_min', '0'),
        decimal('partial_max'), decimal('minimum_remaining', '0'),
        contract.get('full_close_odd_lot') is True)


def original_native_snapshot(history, family, adapter, *, prepared_action=None, prepared_target=None):
    """Resolve each original add to its sealed fill and actual native position.

    ``family`` must have been restored by FamilyRegistry from ``history``. We
    also bind its exact published body here; an in-memory caller cannot append
    an unrecorded child to this read model.
    """
    snapshots = [e for e in history.rows if e.kind is EventKind.POSITION_FAMILY
        and e.producer == 'vati-position-family' and e.correlation_id == family.family_id
        and e.hash == canonical_hash(e.body())
        and all(e.payload.get(k) == family.body().get(k) for k in
                ('family_id', 'account_alias', 'symbol', 'direction', 'opened_ms',
                 'members', 'family_version'))]
    if (not snapshots or family.account_alias != history.account_alias
            or adapter.account_alias != history.account_alias or adapter.venue != history.venue):
        raise FamilyActionError('original family publication/account binding is unavailable')
    original = snapshots[-1]
    receipts = tuple(history.events(EventKind.EXECUTION_RECEIPT))
    root = family.members[0]
    roots = {e.payload.get('broker_position_id') for e in receipts
        if e.correlation_id == root.trade_intent_id and not e.payload.get('exit_action')
        and e.payload.get('status') in {'FILLED', 'PARTIAL'}
        and Decimal(str(e.payload.get('filled_qty'))) == root.quantity
        and Decimal(str(e.payload.get('average_fill'))) == root.price}
    if len(roots) != 1 or None in roots:
        raise FamilyActionError('original root native position is ambiguous')
    restored = FamilyRegistry().restore(history, family_id=family.family_id,
        trade_intent_id=root.trade_intent_id, symbol=family.symbol, direction=family.direction,
        position_id=next(iter(roots)))
    if restored is None or [m.body() for m in restored.members] != [m.body() for m in family.members]:
        raise FamilyActionError('family members are not the authentic committed membership')
    positions = tuple(adapter.positions())
    if len({p.position_id for p in positions}) != len(positions):
        raise FamilyActionError('native position observation has duplicate identities')
    requests = {e.hash: e for e in history.rows if e.kind is EventKind.EXIT_ATTEMPT
        and e.producer == 'vati-execution-router' and e.hash == canonical_hash(e.body())
        and e.payload.get('version') == EXIT_VERSION and e.payload.get('state') == 'REQUESTED'}
    prepared_ref=None
    if prepared_action is not None or prepared_target is not None:
        from vati.lifecycle.family_action_journal import target_ref
        if (prepared_action is None or prepared_target is None
                or prepared_action.hash!=canonical_hash(prepared_action.body())
                or not any(e.hash==prepared_action.hash for e in history.rows)
                or prepared_action.correlation_id!=family.family_id
                or prepared_target.body() not in prepared_action.payload['plan']['targets']):
            raise FamilyActionError('current prepared native request lacks original family action/target')
        matches=[request for request in requests.values()
            if request.payload.get('family_action_ref')==prepared_action.hash
            and request.payload.get('family_target_ref')==target_ref(prepared_action.hash,prepared_target.body())]
        if len(matches)!=1 or any(e.kind is EventKind.EXIT_ATTEMPT
                and e.payload.get('request_ref')==matches[0].hash for e in history.rows):
            raise FamilyActionError('current prepared native request is not a unique unobserved dispatch')
        prepared_ref=matches[0].hash
    used = set(); legs = []; ambiguous = False
    for member in family.members:
        if not member.adds:
            continue
        command = history.commands.get(member.trade_intent_id)
        matches = [e for e in receipts if not e.payload.get('exit_action')
            and e.payload.get('status') in {'FILLED', 'PARTIAL'}
            and e.correlation_id == member.trade_intent_id
            and e.received_time_ms <= member.occurred_ms
            and Decimal(str(e.payload.get('filled_qty'))) == member.quantity
            and Decimal(str(e.payload.get('average_fill'))) == member.price]
        # Equal quantity/price fills are not disambiguated by arrival order.
        unique = {e.payload['receipt_hash']: e for e in matches}
        if command is None or len(unique) != 1:
            raise FamilyActionError('original native family membership is ambiguous')
        entry = next(iter(unique.values())); pid = entry.payload.get('broker_position_id')
        if not pid or pid in used:
            raise FamilyActionError('original entries do not identify distinct native family legs')
        used.add(pid)
        refs = [original.hash, history.command_refs[member.trade_intent_id], entry.hash]
        remainder = Fraction(member.quantity); uncertain = False
        consumed = set()
        for exit in receipts:
            r = exit.payload
            if (r.get('exit_action') != 'CLOSE' or r.get('broker_position_id') != pid
                    or exit.correlation_id != member.trade_intent_id):
                continue
            from vati.execution.native_protection import original_native_protection
            native_protection=original_native_protection(history,exit)
            if native_protection is not None:
                if r['receipt_hash'] not in consumed:
                    qty=Decimal(str(r.get('filled_qty','0')))
                    if not qty.is_finite() or qty<=0 or Fraction(qty)>remainder:
                        raise FamilyActionError('original native protection exceeds its own leg')
                    remainder-=Fraction(qty);consumed.add(r['receipt_hash'])
                refs.extend((native_protection.hash,exit.hash))
                continue
            request = requests.get(r.get('exit_request_ref'))
            if (request is None or request.payload.get('position_id') != pid
                    or request.payload.get('trade_intent_id') != member.trade_intent_id
                    or request.payload.get('venue') != history.venue):
                uncertain = True; continue
            outcomes = [e for e in history.rows if e.kind is EventKind.EXIT_ATTEMPT
                and e.producer == 'vati-execution-router' and e.hash == canonical_hash(e.body())
                and e.payload.get('request_ref') == request.hash
                and e.payload.get('receipt_event_ref') == exit.hash]
            if len(outcomes) != 1:
                uncertain = True; continue
            state = outcomes[0].payload.get('state')
            if state not in {'CONFIRMED', 'PARTIAL_CONFIRMED', 'NOT_EXECUTED'}:
                uncertain = True
            if r['receipt_hash'] not in consumed:
                qty = Decimal(str(r.get('filled_qty', '0')))
                if not qty.is_finite() or qty < 0 or Fraction(qty) > remainder:
                    raise FamilyActionError('original close facts exceed their native leg')
                remainder -= Fraction(qty); consumed.add(r['receipt_hash'])
            refs.extend((request.hash, exit.hash, outcomes[0].hash))
        # A currently unchanged position does not settle an earlier request
        # whose effect/reply is still unknown. Bind that original obligation;
        # automatic partial allocation cannot treat it as a known sibling.
        for request in requests.values():
            if (request.payload.get('position_id')!=pid or request.payload.get('venue')!=history.venue
                    or request.payload.get('trade_intent_id') not in {'',member.trade_intent_id}):
                continue
            outcomes=[e for e in history.rows if e.kind is EventKind.EXIT_ATTEMPT
                and e.producer=='vati-execution-router' and e.hash==canonical_hash(e.body())
                and e.payload.get('request_ref')==request.hash]
            refs.append(request.hash)
            if outcomes:refs.append(outcomes[-1].hash)
            if request.hash!=prepared_ref and (not outcomes or outcomes[-1].payload.get('state') not in {'CONFIRMED','PARTIAL_CONFIRMED','NOT_EXECUTED'}):
                uncertain=True
        position = next((p for p in positions if p.position_id == pid), None)
        known = not uncertain
        if position is None:
            known = known and remainder == 0
        elif (history.position_command(position) is None
                or position.trade_intent_id != member.trade_intent_id
                or position.symbol != family.symbol or position.direction != family.direction
                or Fraction(position.quantity) != remainder):
            known = False
        if not known:
            ambiguous = True
        stop = position.stop_price if position else None
        protected = bool(position is not None and stop is not None
            and entry.payload.get('protective_stop_confirmed') is True)
        legs.append(FamilyLeg(pid, member.trade_intent_id,
            exact_decimal(remainder) if known else None, member.price, stop, protected,
            tuple(dict.fromkeys(refs)), _close_rules(adapter, position) if position else None))
    return FamilySnapshot(family.family_id, original.hash, history.account_alias, history.venue,
        family.symbol, family.direction.value, tuple(legs), (original.hash,), ambiguous)
