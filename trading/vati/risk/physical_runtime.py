"""Committed physical baseline/streak projection for native snapshot producers.

Reuse the chain verifier and consume new decision/basis rows incrementally.
Rare close/control changes rebuild the original financial join; a tick never
rehashes the entire history just because a new shared snapshot was displayed.
The enclosing runtime retains its native writer lease and every entry gate.
"""
from vati.core import EventKind
from vati.core.ledger import committed_source_snapshot, LedgerError
from vati.risk.account_context import inspect_context
from vati.risk.native_history import (
    _from_original_event, _original_mt5_query, _original_nonfinancial_rejection,
    NativeRiskSourceUnavailable,
)
from vati.risk.history_scope import CONTROL_EVENTS
from vati.risk.physical_baselines import PhysicalRiskBasisBook, BASIS_EVENT
from vati.risk.physical_history import physical_financial_history, _fact, _control_context
from vati.risk.physical_lockouts import PhysicalLossStreakGovernor


class PhysicalRiskRuntime:
    def __init__(self, ledger, context, policy, *, now_ms):
        self.ledger, self.context, self.policy = ledger, context, policy
        self._queries = {}
        self._now = now_ms
        self._reload(context, now_ms)

    def _reload(self, context, now_ms):
        from decimal import Decimal
        from vati.execution.review import economic_outcome_final
        with committed_source_snapshot(self.ledger):
            history = physical_financial_history(self.ledger, context, available_at_ms=now_ms)
            self.book = PhysicalRiskBasisBook(history)
            self.streaks = PhysicalLossStreakGovernor(self.policy, account_alias=context.account_alias)
            self.streaks.native_account_context = context
            self.streaks.recovery_issue = history.issue
            for fact in history.facts:
                p = fact.payload
                if fact.kind == 'TRADE_REVIEW':
                    self.streaks.on_close(p['strategy_id'], Decimal(p['pnl']), fact.event_time_ms,
                        origin_alias=fact.origin_alias,
                        profit_final=economic_outcome_final(p.get('maturity'), p.get('pnl_basis')))
                elif fact.kind == 'SESSION' and p.get('event') == 'LOSS_STREAK_RESET':
                    self.streaks._reset_original_alias(p['scope'], fact.origin_alias)
            rows = tuple(self.ledger.iter_after(0))
            self._seq = max((seq for seq, _ in rows), default=0)
            self._future = any(max(e.event_time_ms, e.received_time_ms) > now_ms for _, e in rows)
            self._trades = {e.correlation_id for _, e in rows if e.kind is EventKind.RISK_DECISION}
            if not self.ledger.verify_incremental()[0]:
                raise LedgerError('physical risk history integrity unavailable')
            self._head = self.ledger.head()
        self.context, self._now = context, now_ms
        self._queries.clear()

    def _validate_context(self, context, now_ms):
        source = inspect_context(context)
        if (context.physical_account_key != self.context.physical_account_key
                or context.monetary_scope_hash != self.context.monetary_scope_hash
                or context.account_alias != self.context.account_alias
                or source['observed_at_ms'] > now_ms):
            raise ValueError('physical risk source binding changed')
        if context.provider == 'MT5':
            cached = self._queries.get(context.monetary_scope_hash, {})
            if context.source_query_ref not in cached:
                self._queries.pop(context.monetary_scope_hash, None)
            query = _original_mt5_query(self.ledger, context, self._queries)
            strip = lambda value: {k:v for k,v in value.items() if k != 'account_alias'}
            if (max(query.event_time_ms, query.received_time_ms) > now_ms
                    or query.payload['source_ref'] != context.observation_ref
                    or strip(query.payload['mark']) != strip(source['mark'])):
                raise ValueError('physical risk current query is unavailable')

    def refresh(self, context, *, now_ms):
        with committed_source_snapshot(self.ledger):
            if not self.ledger.verify_incremental()[0]:
                raise LedgerError('physical risk ledger integrity unavailable')
            self._validate_context(context, now_ms)
            rows = tuple(self.ledger.iter_after(self._seq))
            reload = self._future or now_ms < self._now
            trades = set(self._trades)
            for _, event in rows:
                p = event.payload
                if event.kind is EventKind.TRADE_REVIEW:
                    reload = True
                elif event.kind is EventKind.SESSION and isinstance(p, dict) and p.get('event') in CONTROL_EVENTS:
                    reload = True
                elif event.kind is EventKind.RISK_DECISION:
                    if event.correlation_id in trades:
                        reload = True  # Reused intent ownership must be rejoined.
                    trades.add(event.correlation_id)
            if not reload:
                for seq, event in rows:
                    if max(event.event_time_ms, event.received_time_ms) > now_ms:
                        reload = True
                        break
                if not reload:
                    for seq, event in rows:
                        try:
                            fact = None
                            if event.kind is EventKind.RISK_DECISION:
                                try:
                                    value = _from_original_event(self.ledger, event,
                                        available_at_ms=now_ms, queries=self._queries)
                                except NativeRiskSourceUnavailable:
                                    if _original_nonfinancial_rejection(event):
                                        continue
                                    raise
                                original = value.context
                                if original.physical_account_key != context.physical_account_key:
                                    continue
                                if original.monetary_scope_hash != context.monetary_scope_hash:
                                    raise ValueError('original risk monetary scope changed')
                                fact = _fact(event, original.account_alias)
                            elif event.kind is EventKind.SESSION and isinstance(event.payload, dict) and event.payload.get('event') == BASIS_EVENT:
                                original = _control_context(self.ledger, event, self._queries)
                                if original.physical_account_key != context.physical_account_key:
                                    continue
                                if original.monetary_scope_hash != context.monetary_scope_hash:
                                    raise ValueError('original basis monetary scope changed')
                                fact = _fact(event, original.account_alias)
                            if fact is not None:
                                self.book._fold(fact)
                        except (KeyError, ValueError, TypeError, ArithmeticError):
                            self.book.unresolved_refs.add(event.hash)
                    self._seq = max((seq for seq, _ in rows), default=self._seq)
                    self._trades = trades
                    self._head = self.ledger.head()
        if reload:
            self._reload(context, now_ms)
        self.context, self._now = context, now_ms
        self.streaks.native_account_context = context
        self.streaks.recovery_issue = self.book.projection(now_ms).issue
        return self.book.projection(now_ms)

    def observe(self, context, *, now_ms, producer):
        """Append a fenced own-origin basis, then independently read it back."""
        before = self.refresh(context, now_ms=now_ms)
        if before.issue:
            return None, before
        planned = self.book.observation_event(context, now_ms=now_ms, producer=producer)
        with self.ledger.atomic():
            if self.ledger.head() != self._head:
                raise LedgerError('physical risk basis changed before append; retry from current source')
            self.ledger.append(planned)
        projection = self.refresh(context, now_ms=now_ms)
        if planned.hash not in self.book._basis or projection.issue:
            raise LedgerError('physical risk basis durable readback unavailable')
        return planned.hash, projection


def project_native_risk(owner, ledger, context, policy, *, now_ms, producer):
    """Shared entry for both producers; errors hold entries, not protection."""
    runtime = getattr(owner, '_physical_risk_runtime', None)
    try:
        if (runtime is None or runtime.policy != policy
                or runtime.context.physical_account_key != context.physical_account_key
                or runtime.context.monetary_scope_hash != context.monetary_scope_hash
                or runtime.context.account_alias != context.account_alias):
            runtime = PhysicalRiskRuntime(ledger, context, policy, now_ms=now_ms)
            owner._physical_risk_runtime = runtime
        ref, values = runtime.observe(context, now_ms=now_ms, producer=producer)
        return ref, values, runtime.streaks, values.issue
    except Exception as exc:
        # A failed cache cannot retain an advanced cursor after partial reads.
        owner._physical_risk_runtime = None
        return None, None, None, 'NATIVE_PHYSICAL_RISK_UNAVAILABLE:' + type(exc).__name__[:64]
