"""Native account/deal reads -> runtime snapshots -> journal -> owner projection."""
from copy import deepcopy
from decimal import Decimal as D
from types import SimpleNamespace as N
from test_native_deal_history import NativeDeals,DEAL
from test_retirement_venue_observations import ctrader
from test_funding_owner_reports import profile
from vati.app.service import SessionService
from vati.app.portfolio import account_states
from vati.core import Ledger
from vati.execution.base import Health
from vati.funding.worker import stop_funding

def native_runtime_book(tmp_path):
    ledger=Ledger(tmp_path/'native.sqlite');transport=NativeDeals();transport.rows=[];transport.deals=[]
    transport.trader.update(balance=10000,balanceVersion=1);clock={'now':1000}
    adapter=ctrader(transport);adapter.clock=lambda:clock['now'];adapter.heartbeat=lambda **_:Health(True,0,clock['now'])
    read_side=ctrader(transport);read_side.clock=adapter.clock
    class Reader:
        def cash_movements(self,**window):return read_side.cash_movements(**window)
        def deal_history(self,**window):return read_side.deal_history(**window)
        def close(self):pass
    adapter.funding_reader=Reader
    service=SessionService.__new__(SessionService);service.learning=None;service.clock=adapter.clock
    service.runner=N(cycle=N(adapter=adapter,ledger=ledger,peak_equity=D('100'),day_start_equity=D('100'),week_start_equity=D('100'),
        kill=N(active=[]),mandate=N(mode=N(value='DEMO_TRADER')),streaks=N(recovery_issue=''),cfg=N(session_id='native-original-session')))
    try:
        service._account_snapshot(1000);assert service._funding_worker.wait_idle()
        transport.trader.update(balance=11000,balanceVersion=2);clock['now']=3000
        row=deepcopy(DEAL);row['closePositionDetail'].update(grossProfit=1200,swap=-100,commission=-100,balance=11000,moneyDigits=2,balanceVersion=2)
        row['closePositionDetail'].pop('pnlConversionFee');transport.deals=[row]
        service._account_snapshot(3000);assert service._funding_worker.wait_idle()
        assert all(name in {'ProtoOATraderReq','ProtoOAAssetListReq','ProtoOAReconcileReq','ProtoOAGetPositionUnrealizedPnLReq','ProtoOACashFlowHistoryListReq'} for name,_ in transport.requests)
        return ledger
    finally:stop_funding(service)

def test_both_native_statement_types_reach_the_existing_owner_account_projection(tmp_path):
    ledger=native_runtime_book(tmp_path);row=account_states(ledger,[profile()])[0]
    assert row['equity']=='110.00' and row['day_pnl'] is None and row['performance_state']=='UNMEASURED'
    funding=row['funding']
    assert funding['native_mark']['observed_at_ms']==3000
    assert funding['native_deals']['deal_count']==1 and funding['native_deals']['deals'][0]['deal']['close']['pnl_conversion_fee'] is None
    assert funding['period']['state']=='MEASURED' and funding['period']['balance_state']=='RECONCILED'
    assert D(funding['period']['performance']['flow_neutral_return'])==D('.1')
    assert funding['period']['return_qualification']=='NOT_ISSUED' and funding['period']['execution_authority'] is False
    assert funding['period']['knowledge_basis']=='LATEST_OBSERVED_HISTORY_NOT_AS_KNOWN_AT_TRADE_TIME'
