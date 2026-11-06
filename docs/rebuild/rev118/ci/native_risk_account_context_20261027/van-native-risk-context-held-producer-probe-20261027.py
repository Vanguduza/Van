from dataclasses import replace
from types import SimpleNamespace as N
import pytest

@pytest.mark.parametrize('producer', ['single','account'])
def test_native_source_failure_keeps_existing_explicit_funding_hold(tmp_path, eurusd, producer):
    from test_funding_risk_fence import book,native,mark
    from test_recoverable_lockouts import _cycle
    from vati.risk.contracts import MarketIntegrityState
    ledger,_,_=book(tmp_path)
    adapter,account=native(replace(mark(3500,equity='98'),native_account_id=99999))
    contract=replace(eurusd,venue='ctrader',account_currency=account.currency)
    if producer=='single':
        service=_cycle(contract,ledger)
        service.cfg=replace(service.cfg,contract=contract,venue='ctrader',account_alias=account.account_alias)
        service.adapter=adapter
        facts=service.snapshot(now_ms=10000,quote_age_ms=17)
    else:
        from vati.app.account_service import AccountCoordinatorService
        service=AccountCoordinatorService.__new__(AccountCoordinatorService)
        service.adapter=adapter;service.account=N();service._ledger=ledger;service.clock=lambda:10000
        service.contracts={'EURUSD':contract};service.peak_equity=account.equity
        service.day_start_equity=account.equity;service.week_start_equity=account.equity
        service._entries={};service.cfg=N(account_alias=account.account_alias,max_quote_age_ms=5000)
        service._ledger_positions=lambda:[];service._risk_store_ok=lambda:True
        service._open_positions=lambda:();service._drawdown_top_state=lambda:None
        service.lifecycle=None;service.consecutive_losses=0;service.kill=N(active=[])
        service.evaluators={'EURUSD':N(last_state=N(as_of_ms=10000,quote_age_ms=17,event_window=None,integrity=MarketIntegrityState.NORMAL))}
        facts=service._snapshot_for(N(symbol='EURUSD',strategy_id=''))
    assert facts.preservation_blocks_new_risk
    assert 'CURRENT_NATIVE_ACCOUNT_BINDING_INVALID' in facts.preservation_reason
    assert facts.native_account_context is None
