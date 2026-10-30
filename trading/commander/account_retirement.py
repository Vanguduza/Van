"""Native local unlink checks; never closes accounts, orders or moves funds."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import time
import uuid

from fastapi import HTTPException
from vati.app.account_lease import AccountRuntimeLease,PostgresLeaseStore,LeaseOutcome,LeaseStoreUnavailable
from vati.app.sqlite_lease import SQLiteLeaseStore
from vati.core import EventKind
from vati.core.canonical import canonical_hash
from vati.core.ledger_pg import open_ledger
from vati.execution.recovery_scope import NativePositionHistory
from vati.execution.exit_journal import ExitJournal
from vati.execution.review import economic_outcome_final


def authority_path(settings):
    value=settings.operation_ledger
    if not value or value==':memory:':
        raise HTTPException(503,'Persistent native account authority is required for local unlink')
    if not value.startswith(('postgres://','postgresql://')) and not Path(value).is_file():
        raise HTTPException(503,'Existing native account history is unavailable; local link retained')
    return value


def lease_store(settings):
    value=authority_path(settings)
    return PostgresLeaseStore(value) if value.startswith(('postgres://','postgresql://')) else SQLiteLeaseStore(value)


def require_idle_runtime(settings,alias):
    store=lease_store(settings)
    try:
        current=store.read(alias)
        if current is not None and current.live_at(int(time.time()*1000)):
            raise HTTPException(409,'Account runtime is active; local unlink unavailable')
    finally:store.close()


def credential_cleanup(settings,registry,account):
    """Delete only a uniquely referenced regular file in the managed directory.

    A local unlink is not authority to revoke an external credential or destroy
    another account's shared access. Return the private target separately.
    """
    reference=account.credential_ref
    if not reference.secrets_file:return ('KEEP_EXTERNAL' if reference.env_var else 'NONE'),None
    target=Path(reference.secrets_file)
    resolved=target.resolve()
    shared=any(a.alias!=account.alias and a.credential_ref.secrets_file
        and Path(a.credential_ref.secrets_file).resolve()==resolved for a in registry.accounts.values())
    if shared:return 'KEEP_SHARED',None
    managed=(Path(settings.secrets_dir)/(account.alias+'.env')).resolve()
    protected={registry.path.resolve()}
    if not str(settings.operation_ledger).startswith(('postgres://','postgresql://')):
        protected.add(Path(settings.operation_ledger).resolve())
    if target.is_symlink() or resolved!=managed or resolved in protected:return 'KEEP_EXTERNAL',None
    if not target.is_file():return 'NONE',None
    return 'DELETE_MANAGED',target


@contextmanager
def retirement_scope(settings,alias):
    """Own an actual lease row, including when no previous row existed.

    Lease -> account operation -> registry is the runtime's submission order.
    A claimed account-operation journal must precede this scope, without holding
    the alias lock; duplicate requests then read the original without reacquiring.
    """
    store=None;lease=None
    try:
        try:store=lease_store(settings)
        except LeaseStoreUnavailable:
            raise HTTPException(409,'Native account authority store is unreachable; local unlink was not dispatched') from None
        lease=AccountRuntimeLease(store,account_alias=alias,instance_id='commander-unlink:'+uuid.uuid4().hex)
        admission=lease.acquire()
        if admission.outcome is LeaseOutcome.STORE_UNREACHABLE:
            raise HTTPException(409,'Native account authority store is unreachable; local unlink was not dispatched')
        if not admission.permits_orders:
            raise HTTPException(409,'Account runtime is active; stop and reconcile before local unlink')
        with lease.submission_guard(lease.epoch) as held:
            if not held:raise HTTPException(409,'Native runtime fence changed; local link retained')
            yield
    finally:
        if lease is not None:lease.release()
        if store is not None:store.close()


def _history(ledger,account):
    history=NativePositionHistory(ledger,account_alias=account.alias,venue=account.router_venue)
    scoped=[e for e in history.rows if e.kind is EventKind.ORDER_COMMAND and e.producer=='vati-execution-router'
            and (e.payload.get('account_alias')==account.alias or not e.payload.get('account_alias'))]
    if any(e.correlation_id not in history.commands for e in scoped):
        raise HTTPException(409,'Original native trade history is ambiguous; local link retained')
    receipts={iid:[] for iid in history.commands}
    for event in history.events(EventKind.EXECUTION_RECEIPT):
        if not event.payload.get('exit_action'):receipts[event.correlation_id].append(event)
    reviews={e.correlation_id:e for e in history.events(EventKind.TRADE_REVIEW)}
    refs=[e.hash for e in scoped]
    for iid,events in receipts.items():
        if not events:raise HTTPException(409,'An original native order outcome is unknown; local link retained')
        quantities=[Decimal(str(e.payload.get('filled_qty','0'))) for e in events]
        if any(not q.is_finite() or q<0 for q in quantities):
            raise HTTPException(409,'Original native order money facts are unknown; local link retained')
        last=events[-1].payload
        no_effect=last.get('status') in {'REJECTED','CANCELLED','EXPIRED'} and all(q==0 for q in quantities)
        if not no_effect:
            review=reviews.get(iid)
            maturity=review.payload.get('maturity',{}) if review else {}
            requested=Decimal(str(history.commands[iid][0]['quantity']))
            if (last.get('status') not in {'FILLED','PARTIAL','OWNER_EXECUTED','BROKER_CONFIRMED'}
                or not 0<quantities[-1]<=requested or any(q>requested for q in quantities)
                or account.broker!='PAPER' or review is None or review.payload.get('broker_ok') is not True
                or not economic_outcome_final(maturity,review.payload.get('pnl_basis'),account_currency=account.currency)):
                raise HTTPException(409,'Native exposure or unsettled original outcome remains; local link retained')
            refs.append(review.hash)
        refs.extend(e.hash for e in events)
    for producer in ('vati-execution-router','vati-account-service','vati-account-lifecycle','vati-cycle'):
        for event in ExitJournal(ledger,producer).unresolved():
            if event.payload.get('venue')==account.router_venue:
                # Legacy unbound exits cannot be assigned to another alias by
                # guessing. Reconciliation must first bind their original effect.
                raise HTTPException(409,'An original protective exit has no proven account disposition; reconcile before local unlink')
    return sorted(set(refs))


def inspect_retirement(settings,registry,account,*,inside_removal=False,operation_id=None,native_ledger=None):
    """Fresh readonly facts, with no inferred zero for unsupported observation."""
    ledger=native_ledger if native_ledger is not None else open_ledger(authority_path(settings));adapter=None;store=None
    try:
        if not inside_removal:
            store=lease_store(settings);current=store.read(account.alias)
            if current is not None and current.live_at(int(time.time()*1000)):
                raise HTTPException(409,'Account runtime is active; local unlink unavailable')
        from commander.account_effects import AccountEffectJournal
        for state in AccountEffectJournal(ledger)._states().values():
            if ('account:'+account.alias in state.intent.targets and state.phase in {'IN_FLIGHT','UNKNOWN'}
                and state.intent.operation_id!=operation_id):
                raise HTTPException(409,'Original account operation is unresolved; local link retained')
        refs=_history(ledger,account)
        if account.broker=='PAPER':
            # This has no broker funds. Simulated history is retained; never
            # construct a fresh PaperAdapter and mistake it for runtime state.
            funds=None
        else:
            from vati.app.service import build_adapter
            adapter=build_adapter(account,registry,deriv_connector=settings.deriv_connector)
            if settings.ctrader_transport_factory and account.broker=='CTRADER':
                adapter.transport=settings.ctrader_transport_factory(not account.demo)
            started=int(time.time()*1000)
            state=adapter.sync_account();positions=adapter.positions()
            orders_reader=getattr(adapter,'orders',None)
            if not callable(orders_reader):raise HTTPException(409,'Native pending-order observation unavailable; local link retained')
            orders=orders_reader();now=int(time.time()*1000);heartbeat=adapter.heartbeat(now_ms=now)
            if (not isinstance(positions,list) or not isinstance(orders,list) or positions or orders):
                raise HTTPException(409,'Native exposure, pending orders or readback is unknown; local link retained')
            if (state.account_alias!=account.alias or state.currency!=account.currency or state.verified is not True
                or heartbeat.connected is not True or type(heartbeat.last_heartbeat_ms) is not int
                or not 0<=now-heartbeat.last_heartbeat_ms<=30000 or not 0<=now-started<=30000
                or (account.broker!='DERIV' and (type(state.server_time_unix_ms) is not int or not 0<=now-state.server_time_unix_ms<=30000))
                or not isinstance(state.balance,Decimal) or not state.balance.is_finite()
                or not isinstance(state.equity,Decimal) or not state.equity.is_finite()):
                raise HTTPException(409,'Native funds, identity or freshness is unknown; local link retained')
            funds={'balance':str(state.balance),'equity':str(state.equity),'currency':state.currency}
        cleanup,_=credential_cleanup(settings,registry,account)
        return {'schema':'vati.local-unlink-review/1','remote_account_closed':False,
                'historical_data_retained':True,'retained_remote_funds':funds,
                'trade_history_ref':canonical_hash(refs),'trade_history_count':len(refs),'credential_cleanup':cleanup}
    except HTTPException:raise
    except Exception:
        raise HTTPException(409,'Native retirement facts unavailable; reconcile before local unlink') from None
    finally:
        if adapter is not None:
            transport=getattr(adapter,'transport',None)
            close=getattr(transport,'close',None)
            if callable(close):close()
            queue=getattr(adapter,'queue',None)
            if queue is not None and callable(getattr(queue,'close',None)):queue.close()
        if store is not None:store.close()
        if native_ledger is None:ledger.close()
