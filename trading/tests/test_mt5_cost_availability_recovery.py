"""Unknown cost is durable; known fills never turn back into unknown orders."""
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal as D

import pytest

from test_single_session_unknown_entry import delayed_native_session, isolated_native_history, pytestmark
from test_postgres_ledger_isolation import pg_dsn
from vati.app.service import SessionService
from vati.app.session_recovery import recover_session
from vati.core import EventKind, make_event
from vati.app.trade_lifecycle import AccountTradeLifecycle


def fill_original(clock, poll, orders, delivered):
    original = orders()[0].correlation_id
    poll(); fields = delivered[0].split('|'); cid = int(fields[0])
    position = {'ticket':900,'symbol':fields[2],'type':fields[3],'volume':fields[4],'price_open':fields[5],
        'sl':fields[6],'tp':fields[7] or 0,'comment':fields[9],'magic':int(fields[10]),'profit':0}
    result = {'id':cid,'status':'FILLED','order':'90001','position':900,'volume':fields[4],
        'price':fields[5],'sl_confirmed':True,'server_time_ms':clock['ms']}
    return original, position, result


@pytest.mark.parametrize('when', ['before-cost','after-cost','none'])
def test_unknown_cost_fact_replays_once_and_real_service_restart_keeps_native_position(tmp_path, eurusd, when):
    with delayed_native_session(tmp_path,eurusd,recorded_costs=False) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original, native, ack = fill_original(clock,poll,orders,delivered)
        cycle = service.runner.cycle
        write = cycle._record_tca
        def interrupted(*args,**kwargs):
            if when == 'after-cost':
                write(*args,**kwargs)
            raise OSError('fixture original cost-availability publication ACK lost')
        if when != 'none':
            cycle._record_tca = interrupted
        poll(results=[ack],positions=[native]);service.step_once()
        assert cycle.protection.stop_of('900') is not None
        if when != 'none':
            assert original in cycle.unresolved_entry_attempts
        cycle._record_tca = write;clock['ms'] += 1;service.step_once()
        assert original not in cycle.unresolved_entry_attempts
        facts = [e for e in service._ledger.iter(EventKind.SESSION,correlation_id=original)
            if e.payload.get('event') == 'TCA_UNAVAILABLE']
        assert len(facts) == 1
        receipts = [e for e in service._ledger.iter(EventKind.EXECUTION_RECEIPT,correlation_id=original)
            if e.payload.get('status') == 'FILLED']
        assert receipts and receipts[-1].payload['fees'] is None
        assert facts[0].payload['source_receipt_hash'] == receipts[-1].payload['receipt_hash']
        assert service._ledger.count(EventKind.TCA_RECORD) == 0 and len(orders()) == 1
        service.close();service._ledger.close()
        restarted = SessionService(service.cfg,lambda now:[],clock=lambda:clock['ms'],adapter=service.adapter).build()
        try:
            restarted.start()
            assert restarted.runner.permit_new_orders and restarted.runner.startup_report.permit_new_orders
            cold = restarted.runner.cycle
            assert cold._entries[original]['fees'] is None and cold._entries[original]['cost_ratio'] is None
            assert cold._entries[original]['recovery_context_complete'] is True
            assert cold.protection.stop_of('900') is not None and cold.thesis.thesis_for(original) is not None
            assert restarted._ledger.count(EventKind.TCA_RECORD) == 0
            assert len([e for e in restarted._ledger.iter(EventKind.SESSION,correlation_id=original)
                if e.payload.get('event') == 'TCA_UNAVAILABLE']) == 1
            assert len(queue.native_entries(service.cfg.account_alias)) == 1
        finally:
            restarted.close();restarted._ledger.close()


@pytest.mark.parametrize('bad_claim', ['wrong-reference','unsupported-schema'])
def test_unrelated_unavailable_cost_claim_cannot_complete_original_native_recovery(tmp_path, eurusd, bad_claim):
    with delayed_native_session(tmp_path,eurusd,recorded_costs=False) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original, native, ack = fill_original(clock,poll,orders,delivered)
        cycle = service.runner.cycle
        write = cycle._record_tca
        cycle._record_tca = lambda *args,**kwargs: (_ for _ in ()).throw(OSError('fixture cost not committed'))
        poll(results=[ack],positions=[native]);service.step_once()
        cycle._record_tca = write
        filled = next(e for e in service._ledger.iter(EventKind.EXECUTION_RECEIPT,correlation_id=original)
            if e.payload.get('status') == 'FILLED')
        service._ledger.append(make_event(EventKind.SESSION,'vati-cycle',
            {'event':'TCA_UNAVAILABLE','reason':'RECORDED_NATIVE_FEES_UNMEASURED',
             'source_receipt_hash':'f'*64 if bad_claim=='wrong-reference' else filled.payload['receipt_hash'],
             'schema':None if bad_claim=='wrong-reference' else 'unsupported-future-schema',
             'account_alias':service.cfg.account_alias},
            event_time_ms=clock['ms'],received_time_ms=clock['ms'],correlation_id=original))
        expected, unresolved = recover_session(cycle,service.adapter.positions())
        assert original in unresolved and cycle.protection.stop_of('900') is not None
        assert cycle._entries[original]['fees'] is None and cycle._entries[original]['recovery_context_complete'] is False
        assert service._ledger.count(EventKind.TCA_RECORD) == 0
        clock['ms'] += 1;service.step_once()
        assert any(e.payload.get('schema') == 'vati.execution-cost-availability/1'
            and e.payload.get('source_receipt_hash') == filled.payload['receipt_hash']
            for e in service._ledger.iter(EventKind.SESSION,correlation_id=original))


@pytest.mark.parametrize('later_status', ['CANCELLED','REJECTED'])
def test_later_zero_effect_receipt_cannot_replace_original_entry_charge_knowledge(tmp_path, eurusd, later_status):
    with delayed_native_session(tmp_path,eurusd,recorded_costs=False) as (service,bars,index,clock,poll,orders,result,queue,delivered):
        original, native, ack = fill_original(clock,poll,orders,delivered)
        poll(results=[ack],positions=[native]);service.step_once()
        entry = next(e for e in service._ledger.iter(EventKind.EXECUTION_RECEIPT,correlation_id=original)
            if e.payload.get('status') == 'FILLED')
        receipt = AccountTradeLifecycle._receipt_from_payload(entry.payload)
        later = replace(receipt,status=later_status,filled_qty=D('0'),average_fill=None,fees=D('0'),receipt_hash='').sealed()
        clock['ms'] += 1
        service._ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-cycle',asdict(later),
            event_time_ms=clock['ms'],received_time_ms=clock['ms'],correlation_id=original))
        recover_session(service.runner.cycle,service.adapter.positions())
        row = service.runner.cycle._entries[original]
        assert row['fees'] is None and row['quantity'] > 0
        assert service.runner.cycle.protection.stop_of('900') is not None
        assert service._ledger.count(EventKind.TCA_RECORD) == 0
