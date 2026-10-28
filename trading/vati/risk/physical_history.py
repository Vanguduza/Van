"""Original physical-account financial facts for the existing risk owners.

This read never rewrites old records or authenticates new financial operations.
Unknown original ownership and unbound historical controls remain explicit.
The runtime must retain current mandate, funding, native and execution gates.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm

from vati.core import EventKind
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import committed_source_snapshot
from vati.risk.history_scope import NATIVE_PRODUCERS, CONTROL_EVENTS
from vati.risk.native_history import native_risk_history_for_context, _original_mt5_query
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.account_context import inspect_context


@dataclass(frozen=True)
class ScopedFinancialFact:
    event_ref: str
    origin_alias: str
    kind: str
    payload_json: str
    event_time_ms: int
    received_time_ms: int

    @property
    def payload(self):
        # A caller can edit its copy, not the immutable retained fact.
        return json.loads(self.payload_json)


@dataclass(frozen=True)
class PhysicalFinancialHistory:
    physical_account_key: str
    monetary_scope_hash: str
    facts: tuple[ScopedFinancialFact, ...]
    unresolved_refs: tuple[str, ...]
    execution_authority: bool = False
    risk_capital_qualified: bool = False

    @property
    def issue(self):
        return ('physical account risk history has unresolved original ownership or control evidence; native reconciliation required'
                if self.unresolved_refs else '')


def _fact(event, alias):
    return ScopedFinancialFact(event.hash, alias, event.kind.value,
        canonical_json(event.payload), event.event_time_ms, event.received_time_ms)


def _valid_review(event):
    p = event.payload
    if (type(event.event_time_ms) is not int or event.event_time_ms < 0
            or type(event.received_time_ms) is not int or event.received_time_ms < 0
            or event.producer not in NATIVE_PRODUCERS['TRADE_REVIEW']
            or event.hash != canonical_hash(event.body()) or not isinstance(p, dict)
            or type(p.get('record_revision', 0)) is not int or p.get('record_revision', 0) != 0
            or p.get('trade_intent_id') not in (None, '', event.correlation_id)):
        return False
    try:
        if (not isinstance(p.get('strategy_id'), str) or not p['strategy_id']
                or not Decimal(str(p['pnl'])).is_finite()
                or p.get('broker_ok') is False
                or p.get('outcome') in {'UNKNOWN','BROKER_FAILURE'}
                or str(p.get('pnl_basis','')).startswith('UNKNOWN')):
            return False
        if p.get('artifact_hash') is not None and p['artifact_hash'] != canonical_hash(
                {k:v for k,v in p.items() if k != 'artifact_hash'}):
            return False
    except (KeyError, ValueError, InvalidOperation):
        return False
    return True


def _control_context(ledger, event, query_cache):
    """Bind the original control's native source, not today's profile."""
    p = event.payload
    if (event.producer not in NATIVE_PRODUCERS['SESSION']
            or event.hash != canonical_hash(event.body())):
        raise ValueError('original control producer or seal is invalid')
    context = NativeAccountRiskContext(**p['native_account_context'])
    source = inspect_context(context)
    cutoff = min(event.event_time_ms, event.received_time_ms)
    if context.account_alias != p['account_alias'] or source['observed_at_ms'] > cutoff:
        raise ValueError('original control native identity or availability is invalid')
    if context.provider == 'MT5':
        query = _original_mt5_query(ledger, context, query_cache)
        omit_alias = lambda value:{k:v for k,v in value.items() if k != 'account_alias'}
        if (max(query.event_time_ms, query.received_time_ms) > cutoff
                or query.payload['source_ref'] != context.observation_ref
                or omit_alias(query.payload['mark']) != omit_alias(source['mark'])):
            raise ValueError('original control source query does not bind its native input')
    if p['event'] == 'DRAWDOWN_RESUMED':
        new_peak = Decimal(str(p['new_peak_equity']))
        if not new_peak.is_finite() or new_peak <= 0 or new_peak != source['equity']:
            raise ValueError('original drawdown control must retain its exact native equity')
    return context


def _applied_control_refs(ledger):
    # This independently verifies archived P256 proofs, original operation
    # lineage and actual effect references. Expiry today never reauthorizes or
    # erases an already-applied historical outcome.
    from vati.app.runtime_control_journal import RuntimeControlJournal
    return {ref:state for state in RuntimeControlJournal(ledger)._states().values()
        if state.phase == 'APPLIED' for ref in state.result['effect_refs']}


def physical_financial_history(ledger, context, *, available_at_ms):
    """Join original closes through sealed approving native input ownership.

    Presentation aliases, an order label alone and a rejected intent cannot
    supply original physical ownership. Native inputs are verified in one
    consistent committed snapshot. Proven foreign accounts are excluded even
    after reuse of an alias. Reused trade IDs with different original owners
    or intents remain unresolved. Controls need their own original binding;
    no alias-scoped reset is applied to a physical aggregate here.
    """
    with committed_source_snapshot(ledger):
        source = native_risk_history_for_context(ledger, context, available_at_ms=available_at_ms)
        rows = tuple(e for e in ledger.iter()
            if max(e.event_time_ms, e.received_time_ms) <= available_at_ms)
        selected_inputs = {v.event_ref:v for v in source.original_inputs}
        # Provenance stays explicitly unknown in the source index. An original
        # hash-bound refusal, however, cannot own financial exposure or clear it.
        unresolved = set(source.unresolved_refs) - set(source.nonfinancial_rejection_refs)
        bindings, approval_availability = {}, {}
        positions = {event.hash:index for index,event in enumerate(rows)}
        # The source reader has evaluated every RISK_DECISION at this cutoff:
        # selected, proven foreign, or explicitly unresolved. Only the first
        # two sets can supply immutable trade ownership.
        for event in rows:
            if event.kind is not EventKind.RISK_DECISION or event.hash in unresolved:
                continue
            p = event.payload
            if p['decision']['decision'] not in {'APPROVED','REDUCED'}:
                continue
            native = p['inputs']['snapshot']['native_account_context']
            intent = p['inputs']['intent']
            owner = (native['physical_account_key'], native['monetary_scope_hash'],
                native['account_alias'], p['decision']['intent_hash'], intent['strategy_id'])
            bindings.setdefault(event.correlation_id, set()).add(owner)
            approval_availability.setdefault((event.correlation_id, owner), []).append(
                (positions[event.hash], max(event.event_time_ms, event.received_time_ms)))
        aliases = {v.context.account_alias for v in source.original_inputs}
        aliases.add(context.account_alias)
        reviews_by_trade = {}
        for event in rows:
            if (event.kind is EventKind.TRADE_REVIEW and isinstance(event.payload, dict)
                    and type(event.payload.get('record_revision', 0)) is int
                    and event.payload.get('record_revision', 0) == 0):
                reviews_by_trade.setdefault(event.correlation_id, set()).add(event.hash)
        duplicate_reviews = set()
        for trade, refs in reviews_by_trade.items():
            if len(refs) > 1 and any(owner[0:2] == (context.physical_account_key, context.monetary_scope_hash)
                                      for owner in bindings.get(trade, ())):
                duplicate_reviews.update(refs)
        out = []
        control_refs, control_queries = None, {}
        direct_controls = {}
        for event in rows:
            p = event.payload
            if event.kind is EventKind.RISK_DECISION:
                value = selected_inputs.get(event.hash)
                if value is not None:
                    out.append(_fact(event, value.context.account_alias))
            elif event.kind is EventKind.TRADE_REVIEW:
                owners = bindings.get(event.correlation_id, set())
                if event.hash in duplicate_reviews or not _valid_review(event) or len(owners) != 1:
                    unresolved.add(event.hash)
                    continue
                physical, monetary, alias, _, strategy = next(iter(owners))
                owner = next(iter(owners))
                if not any(index < positions[event.hash]
                        and known_at <= min(event.event_time_ms, event.received_time_ms)
                        for index,known_at in approval_availability.get((event.correlation_id, owner), ())):
                    unresolved.add(event.hash)
                    continue
                if (p.get('account_alias') not in (None, '', alias)
                        or p['strategy_id'] != strategy):
                    unresolved.add(event.hash)
                    continue
                if physical != context.physical_account_key:
                    continue
                if monetary != context.monetary_scope_hash:
                    unresolved.add(event.hash)
                    continue
                maturity = p.get('maturity')
                if isinstance(maturity, dict) and maturity.get('source') == 'DETERMINISTIC_PAPER_SETTLEMENT':
                    # The paper finality producer cannot settle a native account,
                    # even when that account is a native broker demo profile.
                    unresolved.add(event.hash)
                    continue
                out.append(_fact(event, alias))
            elif event.kind is EventKind.SESSION and isinstance(p, dict) and p.get('event') == 'NATIVE_RISK_BASIS':
                try:
                    original = _control_context(ledger, event, control_queries)
                    if original.physical_account_key != context.physical_account_key:
                        continue
                    if original.monetary_scope_hash != context.monetary_scope_hash:
                        raise ValueError('original basis monetary scope is different')
                    out.append(_fact(event, original.account_alias))
                except (KeyError, ValueError, TypeError, ArithmeticError, RuntimeError):
                    unresolved.add(event.hash)
            elif event.kind is EventKind.SESSION and isinstance(p, dict) and p.get('event') in CONTROL_EVENTS:
                if ('native_account_context' in p or p.get('account_alias') in aliases
                        or not p.get('account_alias')):
                    try:
                        original = _control_context(ledger, event, control_queries)
                        if 'original_owner_control' in p:
                            from vati.risk.control_archive import validate_original_control
                            identity = validate_original_control(event)
                            direct_controls.setdefault(identity, []).append(event.hash)
                        else:
                            if control_refs is None:
                                control_refs = _applied_control_refs(ledger)
                            proof = control_refs.get(event.hash)
                            if (proof is None or proof.intent.account_alias != original.account_alias
                                    or proof.authority_ref != p['owner_signature_ref']
                                    or proof.proof.operation_id != p['operation_id']):
                                raise ValueError('original applied control receipt unavailable')
                        if original.physical_account_key != context.physical_account_key:
                            continue
                        if original.monetary_scope_hash != context.monetary_scope_hash:
                            raise ValueError('original control monetary scope is different')
                        out.append(_fact(event, original.account_alias))
                    except (KeyError, ValueError, TypeError, ArithmeticError, RuntimeError,
                            InvalidSignature, UnsupportedAlgorithm):
                        unresolved.add(event.hash)
        duplicates = {ref for refs in direct_controls.values() if len(refs) > 1 for ref in refs}
        unresolved.update(duplicates)
        out = [fact for fact in out if fact.event_ref not in duplicates]
        return PhysicalFinancialHistory(context.physical_account_key,
            context.monetary_scope_hash, tuple(out), tuple(sorted(unresolved)))
