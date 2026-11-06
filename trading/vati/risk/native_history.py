"""Original native risk inputs for physical-account history reconstruction.

This reader does not merge financial histories, apply owner resets, qualify
capital or issue order authority. Historical approvals remain source facts
after expiry; a caller must obtain fresh authority for any new operation.
"""
from dataclasses import dataclass
import re

from vati.core import EventKind
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import committed_source_snapshot
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context, validate_snapshot_context
from vati.risk.authority import _canonical_hash
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.serde import snapshot_from_dict

_DIGEST = re.compile(r'[0-9a-f]{64}', re.ASCII)
_PRODUCERS = frozenset({'vati-cycle', 'vati-account-coordinator'})


class NativeRiskSourceUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class NativeRiskInput:
    event_ref: str
    trade_intent_id: str
    decision_hash: str
    recorded_decision: str
    intent_account_alias: str
    context: NativeAccountRiskContext
    snapshot_json: str
    event_time_ms: int
    received_time_ms: int
    execution_authority: bool = False
    risk_capital_qualified: bool = False


def original_native_risk_input(ledger, event_ref: str, *, available_at_ms: int) -> NativeRiskInput:
    """Read an original sealed snapshot and independently join its MT5 receipt.

    Missing native context stays unbound. Neither the current configuration
    nor an account's display alias can supply an absent historical identity.
    The returned decision is a historical outcome, never a replayable grant.
    """
    if not isinstance(event_ref, str) or _DIGEST.fullmatch(event_ref) is None:
        raise NativeRiskSourceUnavailable('original native risk event reference is invalid')
    native_int(available_at_ms, minimum=0)
    with committed_source_snapshot(ledger):
        if not ledger.verify_chain()[0]:
            raise NativeRiskSourceUnavailable('original native risk ledger integrity is unavailable')
        rows = [e for e in ledger.iter(EventKind.RISK_DECISION) if e.hash == event_ref]
        if len(rows) != 1:
            raise NativeRiskSourceUnavailable('original native risk record is unavailable')
        return _from_original_event(ledger, rows[0], available_at_ms=available_at_ms, queries={})


def _from_original_event(ledger, event, *, available_at_ms, queries):
    if event.producer not in _PRODUCERS or event.hash != canonical_hash(event.body()):
        raise NativeRiskSourceUnavailable('original native risk producer or seal is invalid')
    native_int(event.event_time_ms, minimum=0)
    native_int(event.received_time_ms, minimum=0)
    if max(event.event_time_ms, event.received_time_ms) > available_at_ms:
        raise NativeRiskSourceUnavailable('original native risk record was not yet available')
    try:
        payload = event.payload
        inputs, decision = payload['inputs'], payload['decision']
        intent = inputs['intent']
        snapshot = snapshot_from_dict(inputs['snapshot'])
        code = decision['decision']
        trade = intent['trade_intent_id']
        if (not isinstance(trade, str) or not trade or trade != event.correlation_id
                or decision['trade_intent_id'] != trade
                or code not in {'APPROVED', 'REDUCED', 'REJECTED'}
                or type(decision.get('approval_schema_version')) is not int
                or decision['approval_schema_version'] != 2
                or canonical_hash(intent) != decision['intent_hash']
                or canonical_hash({k: v for k, v in decision.items() if k != 'decision_hash'}) != decision['decision_hash']
                or _canonical_hash(snapshot) != decision['risk_snapshot_hash']):
            raise NativeRiskSourceUnavailable('original native risk inputs do not match their decision')
        context = snapshot.native_account_context
        if context is None:
            raise NativeRiskSourceUnavailable('original risk record has no native account binding')
        source = inspect_context(context)
        validate_snapshot_context(snapshot)
        native_int(snapshot.now_unix, minimum=0)
        original_time = min(event.event_time_ms, event.received_time_ms)
        if (snapshot.now_unix * 1000 > original_time or source['observed_at_ms'] > original_time
                or snapshot.account_verified is not True
                or payload.get('account_alias', snapshot.account_alias) != snapshot.account_alias):
            raise NativeRiskSourceUnavailable('original native account observation does not bind the record')
        if code in {'APPROVED', 'REDUCED'} and (
                intent['account_alias'] != snapshot.account_alias
                or intent['venue'] != snapshot.symbol_contract.venue):
            raise NativeRiskSourceUnavailable('original approving risk input has conflicting account ownership')
        if context.provider == 'MT5':
            query = _original_mt5_query(ledger, context, queries)
            omit_alias = lambda value: {k: v for k, v in value.items() if k != 'account_alias'}
            if (query.received_time_ms > original_time or query.event_time_ms > original_time
                    or query.payload['source_ref'] != context.observation_ref
                    or omit_alias(query.payload['mark']) != omit_alias(source['mark'])):
                raise NativeRiskSourceUnavailable('original native MT5 query does not bind the historical input')
        return NativeRiskInput(event.hash, trade, decision['decision_hash'], code,
            intent['account_alias'], context, canonical_json(inputs['snapshot']),
            event.event_time_ms, event.received_time_ms)
    except NativeRiskSourceUnavailable:
        raise
    except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError) as exc:
        raise NativeRiskSourceUnavailable('original native risk input is malformed') from exc


def _original_mt5_query(ledger, context, queries):
    from vati.funding.mt5_journal import Mt5FundingBook
    scope = context.monetary_scope_hash
    if scope not in queries:
        queries[scope] = {e.hash: e for e in Mt5FundingBook(ledger)._queries(scope)}
    query = queries[scope].get(context.source_query_ref)
    if query is None:
        raise NativeRiskSourceUnavailable('original native MT5 query receipt is unavailable')
    return query


@dataclass(frozen=True)
class NativeRiskHistory:
    """Original input provenance for one physical account and monetary scope.

    This deliberately does not apply alias-scoped owner resets, fold trade
    outcomes, share collateral, reserve money or issue a new financial grant.
    Unbound records require reconciliation before a financial consumer can
    claim complete history. Original labels and immutable references survive.
    """
    anchor_event_ref: str | None
    physical_account_key: str
    monetary_scope_hash: str
    original_inputs: tuple[NativeRiskInput, ...]
    unresolved_refs: tuple[str, ...]
    execution_authority: bool = False
    risk_capital_qualified: bool = False
    nonfinancial_rejection_refs: tuple[str, ...] = ()


def original_native_risk_history(ledger, anchor_event_ref: str, *, available_at_ms: int) -> NativeRiskHistory:
    """Select history from original evidence, never from current configuration.

    One committed snapshot and one full chain verification cover the batch.
    Each original MT5 scope is independently read once. Other proven physical
    accounts are excluded; the same physical account with conflicting monetary
    scope remains unresolved. Unknown original identity cannot be guessed away.
    Availability is bounded by the requested original knowledge time.
    """
    if not isinstance(anchor_event_ref, str) or _DIGEST.fullmatch(anchor_event_ref) is None:
        raise NativeRiskSourceUnavailable('original native risk event reference is invalid')
    native_int(available_at_ms, minimum=0)
    with committed_source_snapshot(ledger):
        if not ledger.verify_chain()[0]:
            raise NativeRiskSourceUnavailable('original native risk ledger integrity is unavailable')
        rows = tuple(ledger.iter(EventKind.RISK_DECISION))
        anchors = [e for e in rows if e.hash == anchor_event_ref]
        if len(anchors) != 1:
            raise NativeRiskSourceUnavailable('original native risk record is unavailable')
        queries = {}
        anchor = _from_original_event(ledger, anchors[0], available_at_ms=available_at_ms, queries=queries)
        return _select_original_inputs(ledger, rows, anchor.context,
            available_at_ms=available_at_ms, queries=queries, anchor=anchor)


def native_risk_history_for_context(ledger, context: NativeAccountRiskContext, *,
                                    available_at_ms: int) -> NativeRiskHistory:
    """Read proven history before the current alias's first risk decision.

    The caller obtains current context from the existing native account
    producer. Its independently retained source receipt is checked here; it
    cannot supply absent identity to an old record. No synthetic risk decision
    is written to bootstrap recovery, and this read grants no capital authority.
    """
    native_int(available_at_ms, minimum=0)
    with committed_source_snapshot(ledger):
        if not ledger.verify_chain()[0]:
            raise NativeRiskSourceUnavailable('original native risk ledger integrity is unavailable')
        try:
            source = inspect_context(context)
            if source['observed_at_ms'] > available_at_ms:
                raise NativeRiskSourceUnavailable('native account source was not yet available')
            queries = {}
            if context.provider == 'MT5':
                query = _original_mt5_query(ledger, context, queries)
                omit_alias = lambda value: {k: v for k, v in value.items() if k != 'account_alias'}
                if (max(query.event_time_ms, query.received_time_ms) > available_at_ms
                        or query.payload['source_ref'] != context.observation_ref
                        or omit_alias(query.payload['mark']) != omit_alias(source['mark'])):
                    raise NativeRiskSourceUnavailable('original native MT5 query does not bind current history source')
            rows = tuple(ledger.iter(EventKind.RISK_DECISION))
            return _select_original_inputs(ledger, rows, context,
                available_at_ms=available_at_ms, queries=queries)
        except NativeRiskSourceUnavailable:
            raise
        except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError) as exc:
            raise NativeRiskSourceUnavailable('native history source context is malformed') from exc


def _select_original_inputs(ledger, rows, context, *, available_at_ms, queries, anchor=None):
    selected, unresolved, rejections = [], [], []
    for event in rows:
        # Later original publications are not facts at an earlier cutoff.
        if max(event.event_time_ms, event.received_time_ms) > available_at_ms:
            continue
        try:
            value = anchor if anchor is not None and event.hash == anchor.event_ref else _from_original_event(
                ledger, event, available_at_ms=available_at_ms, queries=queries)
        except NativeRiskSourceUnavailable:
            unresolved.append(event.hash)
            if _original_nonfinancial_rejection(event):
                rejections.append(event.hash)
            continue
        if value.context.physical_account_key != context.physical_account_key:
            continue
        if value.context.monetary_scope_hash != context.monetary_scope_hash:
            unresolved.append(event.hash)
            continue
        selected.append(value)
    return NativeRiskHistory(None if anchor is None else anchor.event_ref,
        context.physical_account_key, context.monetary_scope_hash, tuple(selected), tuple(unresolved),
        nonfinancial_rejection_refs=tuple(rejections))


def _original_nonfinancial_rejection(event):
    """A hash-bound original refusal has no capital/execution ownership.

    Its unknown native identity stays in unresolved_refs. The additional
    category lets a financial consumer retain that fact without treating an
    original refusal as financial exposure. A close without its own approving
    input still remains unresolved.
    """
    try:
        p = event.payload
        inputs, decision = p['inputs'], p['decision']
        request = inputs['intent']
        snapshot = snapshot_from_dict(inputs['snapshot'])
        trade = request['trade_intent_id']
        return bool(event.producer in _PRODUCERS and event.hash == canonical_hash(event.body())
            and isinstance(trade, str) and trade and trade == event.correlation_id
            and decision['trade_intent_id'] == trade and decision['decision'] == 'REJECTED'
            and type(decision.get('approval_schema_version')) is int
            and decision['approval_schema_version'] == 2
            and canonical_hash(request) == decision['intent_hash']
            and canonical_hash({k:v for k,v in decision.items() if k != 'decision_hash'}) == decision['decision_hash']
            and _canonical_hash(snapshot) == decision['risk_snapshot_hash'])
    except (KeyError, ValueError, TypeError, ArithmeticError, AttributeError):
        return False
