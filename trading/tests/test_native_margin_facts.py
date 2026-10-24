"""An absent margin fact is not a solvent native margin account."""
from decimal import Decimal
from dataclasses import replace
import pytest
from conftest import snapshot,intent,mandate_dict
from vati.risk import RiskAuthority,Decision,TradingMandate
from vati.risk.serde import snapshot_to_dict,snapshot_from_dict


def test_missing_native_margin_is_not_an_approval(eurusd):
    authority=RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
    result=authority.evaluate_safe(intent(),snapshot(eurusd,used_margin=None,free_margin=None,margin_level_pct=None))
    assert result.decision is Decision.REJECTED and result.reason_code=='MARGIN_UNKNOWN',result


def test_original_decimal_margin_facts_survive_replay_without_turning_into_strings(eurusd):
    m=TradingMandate.from_mapping(mandate_dict())
    native=snapshot(eurusd,used_margin=Decimal('2000'),free_margin=Decimal('8000.01001'),margin_level_pct=Decimal('500.000001'))
    before=RiskAuthority(m).evaluate_safe(intent(),native)
    assert before.decision in {Decision.APPROVED,Decision.REDUCED}
    restored=snapshot_from_dict(snapshot_to_dict(native))
    after=RiskAuthority(m).evaluate_safe(intent(),restored)
    assert after==before


@pytest.mark.parametrize('field',['used_margin','free_margin','margin_level_pct'])
def test_partially_missing_leveraged_margin_cannot_be_filled_with_a_healthy_default(eurusd,field):
    m=TradingMandate.from_mapping(mandate_dict());native=snapshot(eurusd,**{field:None})
    result=RiskAuthority(m).evaluate_safe(intent(),native)
    assert result.decision is Decision.REJECTED and result.reason_code=='MARGIN_UNKNOWN'


@pytest.mark.parametrize('field',['used_margin','free_margin','margin_level_pct'])
@pytest.mark.parametrize('value',[True,'10000',Decimal('NaN'),Decimal('Infinity')])
def test_invalid_native_margin_amounts_are_not_capacity(eurusd,field,value):
    result=RiskAuthority(TradingMandate.from_mapping(mandate_dict())).evaluate_safe(intent(),snapshot(eurusd,**{field:value}))
    assert result.decision is Decision.REJECTED and result.reason_code=='MARGIN_INVALID'


@pytest.mark.parametrize('equity,used,raw_free,raw_level,reason',[
    ('150','100','1050','1150','MARGIN_FLOOR'),
    ('90','100','990','1090','MARGIN_CALL'),
    ('100','0','0','0','NO_FREE_MARGIN'),
])
def test_credit_in_reported_margin_cannot_replenish_cash_backed_risk_capacity(eurusd,equity,used,raw_free,raw_level,reason):
    native=snapshot(eurusd,equity=Decimal(equity),balance=Decimal(equity),peak_equity=Decimal(equity),
        day_start_equity=Decimal(equity),week_start_equity=Decimal(equity),used_margin=Decimal(used),
        free_margin=Decimal(raw_free),margin_level_pct=None if used=='0' else Decimal(raw_level))
    result=RiskAuthority(TradingMandate.from_mapping(mandate_dict())).evaluate_safe(intent(),native)
    assert result.decision is Decision.REJECTED and result.reason_code==reason


def test_flat_native_margin_has_a_real_zero_commitment_without_a_fabricated_healthy_ratio(eurusd):
    native=snapshot(eurusd,used_margin=Decimal('0'),free_margin=Decimal('10000'),margin_level_pct=None)
    m=TradingMandate.from_mapping(mandate_dict())
    result=RiskAuthority(m).evaluate_safe(intent(),native)
    assert result.decision in {Decision.APPROVED,Decision.REDUCED}
    restored=snapshot_from_dict(snapshot_to_dict(native))
    assert restored.used_margin==0 and restored.margin_level_pct is None
    assert RiskAuthority(m).evaluate_safe(intent(),restored)==result


def test_absent_added_margin_field_preserves_legacy_snapshot_hash_and_serialization(eurusd):
    from dataclasses import asdict
    from vati.risk.authority import _canonical_hash
    native=snapshot(eurusd,used_margin=None)
    legacy=asdict(native);legacy.pop('used_margin')
    assert 'used_margin' not in snapshot_to_dict(native)
    assert _canonical_hash(native)==_canonical_hash(legacy)
    assert _canonical_hash(snapshot_from_dict(snapshot_to_dict(native)))==_canonical_hash(legacy)


def test_signed_worker_original_margin_fields_reach_the_actual_native_adapter(tmp_path):
    from test_mt5_worker_funding import connection,CashMt5
    class Margined(CashMt5):
        def account_info(self):
            a=super().account_info();a.margin=1000.125;a.margin_free=9250.375;a.margin_level=1024.9218847644045;return a
    sdk,worker,adapter,now=connection(tmp_path,Margined())
    account=adapter.sync_account()
    assert account.used_margin==Decimal('1000.125') and account.free_margin==Decimal('9250.375')
    assert account.margin_level_pct==Decimal('1024.9218847644045')
    assert not sdk.sent


def test_missing_cash_history_does_not_make_known_broker_credit_into_risk_equity(tmp_path):
    from test_mt5_worker_funding import connection,CashMt5
    sdk,worker,adapter,now=connection(tmp_path)
    sdk.history_deals_get=lambda *a,**kw:None
    account=adapter.sync_account()
    assert account.funding_mark is None and account.equity==Decimal('10000')
    assert not sdk.sent


def test_ctrader_native_position_margin_keeps_independent_precision_and_credit_exclusion():
    from test_ctrader_money_precision import NativeFunds
    from test_retirement_venue_observations import ctrader
    native=NativeFunds();native.trader['totalMarginCalculationType']='SUM';native.positions[0].update(usedMargin=123456789,moneyDigits=8)
    account=ctrader(native).sync_account()
    assert account.used_margin==Decimal('1.23456789')
    assert account.free_margin==Decimal('74.29633211') and account.margin_level_pct>6000


@pytest.mark.parametrize('defect',['missing','bool','negative','missing_digits','changed'])
def test_unknown_or_changed_ctrader_margin_is_not_available_capacity(defect):
    from test_ctrader_money_precision import NativeFunds
    from test_retirement_venue_observations import ctrader
    from vati.execution.base import VenueUnavailable
    native=NativeFunds();native.trader['totalMarginCalculationType']='SUM';native.positions[0].update(usedMargin=123456789,moneyDigits=8)
    if defect=='missing':native.positions[0].pop('usedMargin')
    elif defect=='bool':native.positions[0]['usedMargin']=True
    elif defect=='negative':native.positions[0]['usedMargin']=-1
    elif defect=='missing_digits':native.positions[0].pop('moneyDigits')
    else:
        original=native.call
        def changed(name,body):
            result=original(name,body)
            if name=='ProtoOAGetPositionUnrealizedPnLReq':native.positions[0]['usedMargin']+=1
            return result
        native.call=changed
        with pytest.raises(VenueUnavailable):ctrader(native).sync_account()
        return
    account=ctrader(native).sync_account()
    assert account.used_margin is None and account.free_margin is None and account.margin_level_pct is None


@pytest.mark.parametrize('mode,total',[(0,'12'),(1,'17'),(2,'7'),('MAX','12'),('SUM','17'),('NET','7')])
def test_ctrader_margin_uses_native_enum_and_per_symbol_hedge_rules(mode,total):
    from vati.execution.ctrader.adapter import CtraderAdapter
    # Symbol1 has long9/short5; symbol2 has only short3. Global netting would
    # incorrectly offset independent instruments. Algo's MAX integer is 1,
    # while the vendored Open API MAX is 0.
    rows=[{'usedMargin':900,'moneyDigits':2,'tradeData':{'symbolId':1,'tradeSide':'BUY'}},
          {'usedMargin':5000,'moneyDigits':3,'tradeData':{'symbolId':1,'tradeSide':'SELL'}},
          {'usedMargin':3,'moneyDigits':0,'tradeData':{'symbolId':2,'tradeSide':2}}]
    assert CtraderAdapter._position_margin(rows,mode)==Decimal(total)


@pytest.mark.parametrize('mode',[None,True,'unknown',3])
def test_ctrader_unknown_margin_mode_does_not_default_to_sum(mode):
    from vati.execution.ctrader.adapter import CtraderAdapter
    row={'usedMargin':1,'moneyDigits':0,'tradeData':{'symbolId':1,'tradeSide':'BUY'}}
    with pytest.raises(ValueError):CtraderAdapter._position_margin([row],mode)
    assert CtraderAdapter._position_margin([],mode)==0


def margin_projection():
    from vati.execution.native_margin import account_margin_body
    from vati.core.events import make_event,EventKind
    from vati.execution.base import AccountState
    # Use the actual native adapter type; no transport/effect is invoked by a read model.
    from vati.execution.mt5_bridge import Mt5BridgeAdapter
    adapter=Mt5BridgeAdapter.__new__(Mt5BridgeAdapter)
    account=AccountState('native',Decimal('1000'),Decimal('1000'),'USD',True,
        used_margin=Decimal('100'),free_margin=Decimal('1100'),margin_level_pct=Decimal('1200'))
    body=account_margin_body(adapter,account,observed_at_ms=1007)
    event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','equity':'1000','margin':body},
        event_time_ms=1000,received_time_ms=1010,correlation_id='native:session')
    return event


def test_owner_margin_distinguishes_original_reported_amounts_and_cash_backed_bounds():
    from vati.execution.native_margin import reported_account_margin
    event=margin_projection();row=reported_account_margin(event,'native')
    assert row['state']=='OBSERVED' and row['free_margin']=='1100' and row['risk_free_margin_bound']=='900'
    assert row['margin_level_pct']=='1200' and row['risk_margin_level_bound_pct']=='1000'
    assert row['snapshot_ref']==event.hash and row['execution_authority'] is False
    assert row['observed_at_ms']==1007 and row['received_at_ms']==1010


@pytest.mark.parametrize('defect',['producer','authority','future','account','missing_money','invented_free_bound','invented_level_bound','wrong_basis'])
def test_owner_margin_rejects_unbound_or_invented_facts(defect):
    from copy import deepcopy
    from vati.execution.native_margin import reported_account_margin
    from vati.core.canonical import canonical_hash
    event=margin_projection();p=deepcopy(event.payload)
    if defect=='producer':event=replace(event,producer='untrusted-import')
    elif defect=='authority':p['margin']['execution_authority']=True
    elif defect=='future':p['margin']['observed_at_ms']=1011
    elif defect=='account':p['margin']['account_alias']='other'
    elif defect=='missing_money':p['margin']['used_margin']=None
    elif defect=='invented_free_bound':p['margin']['risk_free_margin_bound']='1100'
    elif defect=='invented_level_bound':p['margin']['risk_margin_level_bound_pct']='1200'
    else:p['margin']['basis']='HISTORICAL_GUESS'
    event=replace(event,payload=p);event=replace(event,hash=canonical_hash(event.body()))
    row=reported_account_margin(event,'native')
    assert row['state']=='UNAVAILABLE' and row['execution_authority'] is False


@pytest.mark.parametrize('used',['3','7','13','17','19'])
def test_calculated_margin_ratios_reach_owner_readback_without_precision_truncation(used):
    from vati.execution.ctrader.adapter import CtraderAdapter
    from vati.execution.base import AccountState
    from vati.execution.native_margin import account_margin_body,reported_account_margin
    from vati.core.events import make_event,EventKind
    from decimal import localcontext
    with localcontext() as context:
        context.prec=80
        level=Decimal('1000')/Decimal(used)*100
    account=AccountState('native',Decimal('1000'),Decimal('1000'),'USD',True,
        used_margin=Decimal(used),free_margin=Decimal('1000')-Decimal(used),margin_level_pct=level)
    body=account_margin_body(CtraderAdapter.__new__(CtraderAdapter),account,observed_at_ms=1007)
    event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','equity':'1000','margin':body},
        event_time_ms=1000,received_time_ms=1010,correlation_id='native:session')
    result=reported_account_margin(event,'native')
    assert result['state']=='OBSERVED' and Decimal(result['risk_margin_level_bound_pct'])==level


def test_actual_book_account_snapshot_supplies_original_margin_to_owner():
    from types import SimpleNamespace as N
    from vati.app.account_service import AccountCoordinatorService
    from vati.execution.paper import PaperAdapter
    from vati.core import Ledger,EventKind
    from vati.execution.native_margin import reported_account_margin
    service=AccountCoordinatorService(N(account_alias='paper',max_quote_age_ms=5000),clock=lambda:1007)
    service.adapter=PaperAdapter(account_alias='paper');service._ledger=Ledger()
    service.account=N(alias='paper');service._account_snapshot(1000)
    event=next(service._ledger.iter(EventKind.ACCOUNT_SNAPSHOT))
    row=reported_account_margin(event,'paper')
    assert row['state']=='SIMULATED' and row['used_margin']=='0'
    assert row['observed_at_ms']==1007 and row['received_at_ms']==1007
    assert row['execution_authority'] is False


def test_native_owner_margin_cannot_attach_to_a_profile_without_a_physical_scope():
    from vati.core import Ledger
    from vati.app.portfolio import account_states
    ledger=Ledger();ledger.append(margin_projection())
    row=account_states(ledger,[{'alias':'native','broker':'MT5','currency':'USD'}])[0]
    assert row['margin']=={'state':'UNAVAILABLE','reason':'NATIVE_SCOPE_UNBOUND','execution_authority':False}


@pytest.mark.parametrize('producer',['single','account'])
def test_actual_risk_snapshot_producers_preserve_native_used_margin(eurusd,producer):
    from types import SimpleNamespace as N
    from test_funding_risk_fence import native
    from test_native_balance_reconciliation import mark
    from vati.core import Ledger
    from vati.risk.contracts import MarketIntegrityState
    adapter,_=native(mark(3000,balance='100',equity='100',version=1))
    original=adapter.sync_account
    adapter.sync_account=lambda:replace(original(),used_margin=Decimal('1.125'),free_margin=Decimal('98.875'),margin_level_pct=Decimal('8888'))
    ledger=Ledger()
    if producer=='single':
        from test_recoverable_lockouts import _cycle
        service=_cycle(eurusd,ledger);service.adapter=adapter
        result=service.snapshot(now_ms=7000,quote_age_ms=0)
    else:
        from vati.app.account_service import AccountCoordinatorService
        service=AccountCoordinatorService(N(account_alias='ctrader_primary',max_quote_age_ms=5000),clock=lambda:7000)
        service.account=N(alias='ctrader_primary');service.adapter=adapter;service._ledger=ledger
        service.contracts={'EURUSD':eurusd};service._entries={}
        service._ledger_positions=lambda:[];service._open_positions=lambda:();service._risk_store_ok=lambda:True
        service._drawdown_top_state=lambda:None
        service.evaluators={'EURUSD':N(last_state=N(quote_age_ms=0,as_of_ms=7000,event_window=None,integrity=MarketIntegrityState.NORMAL))}
        result=service._snapshot_for(N(symbol='EURUSD',strategy_id=''))
    assert result.used_margin==Decimal('1.125') and result.free_margin==Decimal('98.875')
    assert result.margin_level_pct==Decimal('8888')
