"""Unavailable native capital evidence must not change future loss limits."""
from decimal import Decimal as D
from types import SimpleNamespace as N
import pytest

from test_funding_risk_fence import book, native, mark, cash
from vati.risk.contracts import MarketIntegrityState


def runtime(producer, adapter, ledger, eurusd, baseline):
    if producer == 'single':
        from test_recoverable_lockouts import _cycle
        service = _cycle(eurusd, ledger)
        service.adapter = adapter
    else:
        from vati.app.account_service import AccountCoordinatorService
        service = AccountCoordinatorService.__new__(AccountCoordinatorService)
        service.adapter = adapter; service.account = N(); service._ledger = ledger
        service.clock = lambda: 7000; service.contracts = {'EURUSD': eurusd}
        service._entries = {}; service.cfg = N(account_alias='ctrader_primary', max_quote_age_ms=5000)
        service._ledger_positions = lambda: []; service._open_positions = lambda: ()
        service._risk_store_ok = lambda: True; service._drawdown_top_state = lambda: None
        service.lifecycle = None; service.consecutive_losses = 0; service.kill = N(active=[])
        from conftest import mandate_dict
        from vati.risk import TradingMandate
        service.mandate = TradingMandate.from_mapping(mandate_dict(account_alias='ctrader_primary',
            venue=adapter.venue, signed_at_unix=1, expires_at_unix=3600))
        service.evaluators = {'EURUSD': N(last_state=N(quote_age_ms=0, as_of_ms=7000,
            event_window=None, integrity=MarketIntegrityState.NORMAL))}
    service.peak_equity = service.day_start_equity = service.week_start_equity = D(baseline)
    return service


def snapshot(service, producer):
    return (service.snapshot(now_ms=7000, quote_age_ms=0) if producer == 'single'
            else service._snapshot_for(N(symbol='EURUSD', strategy_id='')))


@pytest.mark.parametrize('producer', ['single', 'account'])
@pytest.mark.parametrize('baseline', ['0', '100'])
def test_held_native_deposit_does_not_seed_or_raise_any_loss_baseline(tmp_path, eurusd, producer, baseline):
    point = mark(3000, balance='200', equity='200', version=2)
    ledger, _, _ = book(tmp_path, cash_rows=[cash()], closing=point)
    adapter, _ = native(point)
    service = runtime(producer, adapter, ledger, eurusd, baseline)
    before = (service.peak_equity, service.day_start_equity, service.week_start_equity)
    value = snapshot(service, producer)
    assert value.preservation_blocks_new_risk and 'FLOW_ADJUSTED_RISK_NOT_QUALIFIED' in value.preservation_reason
    assert value.equity == 200, 'original native observation must remain available'
    assert (service.peak_equity, service.day_start_equity, service.week_start_equity) == before
    assert (value.peak_equity, value.day_start_equity, value.week_start_equity) == before


@pytest.mark.parametrize('producer', ['single', 'account'])
def test_qualified_native_observation_can_seed_the_original_baselines(tmp_path, eurusd, producer):
    ledger, _, _ = book(tmp_path)
    adapter, _ = native(mark(3500, equity='97'))
    service = runtime(producer, adapter, ledger, eurusd, '0')
    value = snapshot(service, producer)
    assert not value.preservation_blocks_new_risk
    assert value.peak_equity == value.day_start_equity == value.week_start_equity == D('97')


@pytest.mark.parametrize('producer', ['single', 'account'])
def test_missing_credit_and_history_preserve_protective_account_reads_without_seeding_risk(tmp_path, eurusd, producer):
    from test_mt5_worker_funding import connection
    from vati.core import Ledger
    sdk, worker, adapter, now = connection(tmp_path)
    now['ms'] = 7000
    original = sdk.account_info
    def missing_credit():
        a = original(); del a.credit; return a
    sdk.account_info = missing_credit
    sdk.history_deals_get = lambda *a, **kw: None
    service = runtime(producer, adapter, Ledger(), eurusd, '0')
    value = snapshot(service, producer)
    assert value.preservation_blocks_new_risk
    assert (service.peak_equity, service.day_start_equity, service.week_start_equity) == (0, 0, 0)
    assert adapter.positions() == [] and not sdk.sent


def test_owner_resume_cannot_turn_unqualified_native_capital_into_a_new_peak(tmp_path, eurusd):
    point = mark(3000, balance='200', equity='200', version=2)
    ledger, _, _ = book(tmp_path, cash_rows=[cash()], closing=point)
    adapter, _ = native(point)
    service = runtime('single', adapter, ledger, eurusd, '300')
    verified = []
    authority = N(verify=lambda *a, **kw: verified.append(kw))
    count = ledger.count()
    with pytest.raises(ValueError, match='FLOW_ADJUSTED_RISK_NOT_QUALIFIED'):
        service.resume_after_drawdown(owner_signature_ref='explicit-source-fixture', authority=authority, now_ms=7000)
    assert len(verified) == 1 and service.peak_equity == 300 and ledger.count() == count


@pytest.mark.parametrize('changed', [False, True])
def test_existing_recovery_actor_requires_current_funding_for_drawdown_rebaseline(tmp_path, eurusd, changed):
    from vati.app.runtime_control_actor import _eligible
    from dataclasses import replace
    point = mark(3000, balance='200', equity='200', version=2) if changed else mark(3500, equity='97')
    ledger, _, _ = book(tmp_path, cash_rows=[cash()] if changed else (), closing=point if changed else None)
    adapter, account = native(point)
    service = runtime('single', adapter, ledger, eurusd, '300')
    service.cfg = replace(service.cfg, account_alias=account.account_alias,
                          contract=replace(eurusd, account_currency=account.currency))
    value = _eligible(service, N(intent=N(action='resume_drawdown', arguments={})), account,
                      adapter.heartbeat(now_ms=7000), (), 7000)
    assert value is (not changed)


@pytest.mark.parametrize('has_earlier_qualified_baseline', [False, True])
def test_restart_does_not_restore_the_known_old_held_funding_baseline_defect(has_earlier_qualified_baseline):
    from vati.core import Ledger, EventKind, make_event
    from vati.risk.lockouts import restore_equity_baselines
    ledger = Ledger()
    def original(ident, peak, held, time):
        ledger.append(make_event(EventKind.RISK_DECISION, 'vati-cycle', {
            'inputs': {'intent': {'account_alias': 'native', 'trade_intent_id': ident},
                       'snapshot': {'peak_equity': peak, 'day_start_equity': peak, 'week_start_equity': peak,
                           'preservation_blocks_new_risk': held,
                           'preservation_reason': 'FUNDING_RISK_UNAVAILABLE:MT5_NATIVE_CASH_HISTORY_UNAVAILABLE' if held else ''}},
            'decision': {'decision': 'REJECTED' if held else 'APPROVED'}},
            event_time_ms=time, received_time_ms=time, correlation_id=ident))
    if has_earlier_qualified_baseline:
        original('qualified-before-outage', '100', False, 1000)
    original('historical-held-gross-credit', '10000', True, 2000)
    before = ledger.count()
    expected = D('100') if has_earlier_qualified_baseline else None
    assert restore_equity_baselines(ledger.iter(), 3000, account_alias='native') == (expected, expected, expected)
    assert ledger.count() == before and ledger.verify_incremental()[0]


