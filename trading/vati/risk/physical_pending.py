"""Original possible fills across aliases of one proven native account.

This is a risk projection, not an order, cash reservation or settlement owner.
Only original native position IDs cover a fill; an order comment cannot do so.
"""
from decimal import Decimal
from fractions import Fraction

from vati.core import EventKind
from vati.core.ledger import committed_source_snapshot, LedgerError
from vati.risk.contracts import PendingRiskCommitment, Direction, LossModel
from vati.risk.serde import contract_from_dict
from vati.risk.physical_orders import physical_order_exposure
from vati.risk.physical_history import physical_financial_history
from vati.risk.arithmetic import fraction,decimal


class PhysicalPendingRisk:
    def __init__(self, ledger, context, *, now_ms):
        self.ledger = ledger
        self.context = context
        self._reload(now_ms)

    def _reload(self, now_ms):
        with committed_source_snapshot(self.ledger):
            self.exposure = physical_order_exposure(self.ledger,self.context,available_at_ms=now_ms)
            history = physical_financial_history(self.ledger,self.context,available_at_ms=now_ms)
            if self.exposure.unresolved_refs or history.unresolved_refs:
                raise ValueError('pending exposure original ownership is unresolved')
            rows = tuple(self.ledger.iter_after(0))
            by_ref = {e.hash:e for _,e in rows}
            self._originals = {}
            for order in self.exposure.orders:
                original = by_ref[order.original_input_ref]
                contract = contract_from_dict(original.payload['inputs']['snapshot']['symbol_contract'])
                cmd = order.command
                if (contract.symbol != cmd['symbol'] or contract.venue != cmd['venue']
                        or contract.loss_model.value != cmd['loss_model']):
                    raise ValueError('pending order contract changed')
                ids = {by_ref[ref].payload.get('broker_position_id') for ref in order.receipt_refs}
                ids.discard(None);ids.discard('')
                self._originals[order.command_ref] = (contract,frozenset(ids))
            self._closed = {by_ref[f.event_ref].correlation_id for f in history.facts if f.kind=='TRADE_REVIEW'}
            self._trades = {o.trade_intent_id for o in self.exposure.orders}
            self._seq = max((s for s,_ in rows),default=0)
            self._future = min((max(e.event_time_ms,e.received_time_ms) for _,e in rows
                                if max(e.event_time_ms,e.received_time_ms)>now_ms),default=None)
            if not self.ledger.verify_incremental()[0]:
                raise LedgerError('pending risk ledger integrity unavailable')
        self._now = now_ms

    def refresh(self, positions, *, now_ms, contracts=None):
        with committed_source_snapshot(self.ledger):
            if not self.ledger.verify_incremental()[0]:
                raise LedgerError('pending risk ledger integrity unavailable')
            rows = tuple(self.ledger.iter_after(self._seq))
            reload = now_ms<self._now or (self._future is not None and now_ms>=self._future)
            for _,event in rows:
                available = max(event.event_time_ms,event.received_time_ms)
                if available>now_ms:
                    self._future = min(available,self._future) if self._future is not None else available
                    continue
                if (event.kind in {EventKind.ORDER_COMMAND,EventKind.EXECUTION_RECEIPT,EventKind.TRADE_REVIEW}
                        or event.kind is EventKind.RISK_DECISION and event.correlation_id in self._trades):
                    reload = True
            if reload:
                self._reload(now_ms)
            else:
                self._seq = max((s for s,_ in rows),default=self._seq)
                self._now = now_ms
            out=[];claimed=set()
            for order in self.exposure.orders:
                if order.state=='NO_EFFECT':continue
                contract,ids = self._originals[order.command_ref]
                cmd = order.command
                direction = Direction(cmd['direction'])
                matches = [p for p in positions if p.broker_position_id and p.broker_position_id in ids
                           and p.symbol==contract.symbol and p.direction is direction]
                matched_ids = {p.broker_position_id for p in matches}
                if claimed.intersection(matched_ids):
                    raise ValueError('native position cannot cover multiple pending commands')
                if len(matches)!=len(matched_ids):
                    raise ValueError('duplicate native position coverage')
                claimed.update(matched_ids)
                covered = sum((fraction(p.stake if contract.loss_model is LossModel.FULL_STAKE else p.lots)
                               for p in matches),Fraction(0))
                if covered<0:
                    raise ValueError('native position coverage unavailable')
                if order.state=='OPEN' and not matches and order.trade_intent_id in self._closed:
                    continue  # Position stop risk only; not cash or fee settlement.
                quantity = decimal(max(Fraction(0),fraction(order.quantity)-covered))
                if quantity==0:continue
                valuation = None
                if contracts is not None:
                    from vati.risk.pending import validate_valuation_contract
                    valuation=contracts.get(contract.symbol.upper())
                    validate_valuation_contract(contract,valuation)
                out.append(PendingRiskCommitment(order.command_ref,order.original_input_ref,order.origin_alias,
                    self.context.physical_account_key,self.context.monetary_scope_hash,order.state,direction,
                    quantity,Decimal(cmd['entry_price']),
                    None if cmd['protective_stop'] is None else Decimal(cmd['protective_stop']),
                    contract,new_position_slots=0 if matches else 1,valuation_contract=valuation))
            return tuple(out)


def project_pending_risk(owner, ledger, context, positions, *, now_ms, contracts):
    """Called only after the existing native context and risk-source gates."""
    try:
        runtime = getattr(owner,'_physical_pending_risk',None)
        if (runtime is None or runtime.ledger is not ledger
                or runtime.context.physical_account_key!=context.physical_account_key
                or runtime.context.monetary_scope_hash!=context.monetary_scope_hash
                or runtime.context.account_alias!=context.account_alias):
            runtime = PhysicalPendingRisk(ledger,context,now_ms=now_ms)
            owner._physical_pending_risk = runtime
        return runtime.refresh(positions,now_ms=now_ms,contracts=contracts),''
    except Exception as exc:
        owner._physical_pending_risk = None
        return (),'NATIVE_PENDING_RISK_UNAVAILABLE:'+type(exc).__name__[:64]
