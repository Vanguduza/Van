"""Enforce the existing risk-owner floor after the proposed isolated margin."""
import pytest

from test_mt5_final_cash_margin import EntryCashSdk,command
from test_mt5_worker_funding import connection
from test_mql_native_function_bodies import ea


@pytest.mark.parametrize('equity,credit,used,required',[
    (1000.,0.,100.,450.),(1000.,0.,100.,400.),(1100.,100.,100.,400.),
])
def test_signed_native_entry_cannot_cross_existing_cash_margin_floor(tmp_path,equity,credit,used,required):
    sdk=EntryCashSdk(equity=equity,credit=credit,used=used,reported_free=equity-used)
    sdk.margin_value=required;sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert not sdk.sent,'native order_send reached at or below the existing projected 200% floor'
    assert receipt.status=='REJECTED' and receipt.filled_qty==0
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_FLOOR:')


def test_signed_native_entry_above_existing_projected_floor_retains_fill(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.)
    sdk.margin_value=399.99;sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='FILLED' and receipt.protective_stop_confirmed and len(sdk.sent)==1


@pytest.mark.parametrize('case',['entry-floor-low','entry-floor-equal','entry-floor-credit','entry-floor-limit',
    'entry-floor-fraction-held','entry-floor-after','entry-floor-final','entry-floor-improved',
    'entry-floor-reported','entry-floor-reported-equal','entry-floor-reported-improved','entry-floor-reported-final'])
def test_actual_ea_entry_keeps_original_projected_floor(ea,case):
    native=ea(case)
    assert native['entry_calls']==0,'actual EA entry function reached a simulated unsafe native send'
    assert native['results'][0]['status']=='REJECTED'
    assert native['results'][0]['reason_code']=='NATIVE_CASH_MARGIN_FLOOR'


def test_actual_ea_entry_above_projected_floor_retains_native_fill(ea):
    native=ea('entry-floor-good')
    assert native['entry_calls']==1 and native['results'][0]['status']=='FILLED'


def test_native_floor_constants_match_the_existing_risk_owner():
    import ast,re
    from pathlib import Path
    from vati.risk.authority import MARGIN_FLOOR_LEVEL_PCT
    root=Path(__file__).resolve().parents[2]
    sdk=ast.parse((root/'deploy/van-trading-core/windows/mt5_worker/mt5_bridge_worker.py').read_text())
    matches=[ast.literal_eval(n.value) for n in sdk.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='NATIVE_ENTRY_MARGIN_FLOOR_LEVEL_PCT' for t in n.targets)]
    ea=(root/'deploy/van-trading-core/mql5/VanBridgeEA.mq5').read_text()
    native=re.findall(r'^const int NATIVE_ENTRY_MARGIN_FLOOR_LEVEL_PCT=(\d+);',ea,re.M)
    assert matches==[200] and native==['200']
    assert MARGIN_FLOOR_LEVEL_PCT==matches[0]==int(native[0])


@pytest.mark.parametrize('field,value',[('entry_equity',500.),('credit',500.),('entry_used',350.)])
def test_projected_floor_deterioration_during_calculation_never_dispatches(tmp_path,field,value):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.)
    sdk.margin_value=200.;sdk.on_margin=lambda:setattr(sdk,field,value)
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_FLOOR:')


def test_original_insufficient_floor_cannot_be_renewed_by_a_better_later_snapshot(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.)
    sdk.margin_value=400.;sdk.on_margin=lambda:setattr(sdk,'entry_equity',2000.)
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_FLOOR:')


def test_final_native_guard_rechecks_projected_floor_before_handoff(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.);original=sdk.account_info
    sdk.margin_value=200.;state={'armed':False,'reads':0}
    def account():
        a=original()
        if state['armed']:
            state['reads']+=1
            if state['reads']>=2:a.margin=350.
        return a
    sdk.account_info=account;sdk.on_margin=lambda:state.update(armed=True)
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert state['reads']==2 and receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_FLOOR:')


@pytest.mark.parametrize('level,required,status',[(210.,10.,'REJECTED'),(220.,10.,'REJECTED'),
    (220.005,10.,'FILLED'),(250.,10.,'FILLED')])
def test_signed_native_reported_lower_level_remains_binding(tmp_path,level,required,status):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.);original=sdk.account_info
    def account():
        a=original();a.margin_level=level;return a
    sdk.account_info=account;sdk.margin_value=required
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status==status and len(sdk.sent)==(1 if status=='FILLED' else 0)
    if status=='REJECTED':assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_FLOOR:')


@pytest.mark.parametrize('level',[None,-1.,float('nan'),float('inf'),True])
def test_unavailable_original_reported_level_never_becomes_healthy(tmp_path,level):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.);original=sdk.account_info
    def account():
        a=original();a.margin_level=level;return a
    sdk.account_info=account;sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_UNAVAILABLE:')


def test_signed_native_subminor_used_margin_retains_original_reported_product(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=.001,reported_free=999.999);sdk.margin_value=1.
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='FILLED' and len(sdk.sent)==1


@pytest.mark.parametrize('case',['entry-floor-reported-good','entry-floor-reported-fraction','entry-floor-subminor'])
def test_actual_ea_original_reported_product_retains_healthy_entry(ea,case):
    native=ea(case);assert native['entry_calls']==1 and native['results'][0]['status']=='FILLED'


@pytest.mark.parametrize('case',['entry-floor-level-missing','entry-floor-level-invalid','entry-floor-level-negative'])
def test_actual_ea_reported_level_unavailable_cannot_grant_entry(ea,case):
    native=ea(case);assert native['entry_calls']==0 and native['results'][0]['status']=='REJECTED'
    assert native['results'][0]['reason_code']=='NATIVE_CASH_MARGIN_UNAVAILABLE'


@pytest.mark.parametrize('improve',[False,True])
def test_original_and_final_reported_margin_floor_both_remain_binding(tmp_path,improve):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.);original=sdk.account_info
    sdk.margin_value=10.;state={'armed':False,'reads':0}
    def account():
        a=original()
        if state['armed']:state['reads']+=1
        a.margin_level=(210. if not state['armed'] else 1000.) if improve else (210. if state['reads']>=2 else 1000.)
        return a
    sdk.account_info=account;sdk.on_margin=lambda:state.update(armed=True)
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='REJECTED' and not sdk.sent
    assert receipt.reject_reason.startswith('NATIVE_CASH_MARGIN_FLOOR:')
