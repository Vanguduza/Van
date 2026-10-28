"""Execute actual EA function bodies against a controlled C++ terminal model.

No reimplementation of EA branches: the source bodies are extracted unchanged.
MetaEditor independently compiles the entire EA. Neither proves broker execution.
"""
import json
import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
EA=ROOT/'deploy/van-trading-core/mql5/VanBridgeEA.mq5'


@pytest.fixture(scope='module')
def ea(tmp_path_factory):
    assert shutil.which('g++'), 'EA function-body controls require g++'
    source=EA.read_text()
    names={'JsonEscape','JsonNumber','NativeRefusal','ResolvePositionTicket',
           'NativeIdentityMatches','NativeEntryDeadline','NativeEntryDeadlineCurrent',
           'NativeBindingJson','CashUnavailable','NativeCashJson','NativeMarginJson',
           'SnapshotJson','PushResult','ExecOrderSend','ExecModifySl','ExecClose',
           'MarginReadAccountScopeJson','NativeUnitsCanonical','NativeUnitsIncrement',
           'NativeMoneyUnitsFromText','NativeUnitsCompare','NativeUnitsSubtract',
           'NativeCashAmount','NativeEntryCashScope','NativeEntryCashBound',
           'NativeCheckCurrentEntryCash','NativePrepareEntryCash'}
    bodies=[]
    for match in re.finditer(r'^(?:string|void|bool|ulong|int) (\w+)\([^{};]*?\)\s*\{',source,re.M):
        if match[1] not in names:
            continue
        # Brace-aware lexer: JSON strings/comments also contain braces.
        at=match.end(); depth=1; quoted=False; escaped=False
        while depth:
            c=source[at]; at+=1
            if escaped: escaped=False
            elif quoted and c=='\\': escaped=True
            elif c=='"': quoted=not quoted
            elif not quoted:
                if c=='{': depth+=1
                elif c=='}': depth-=1
        # Only array-reference ABI spelling changes for the C++ interface;
        # each actual function body remains byte-identical to the EA source.
        header=source[match.start():match.end()]
        header=re.sub(r'const string &(\w+)\[\]',r'const std::vector<string> &\1',header)
        bodies.append(header+source[match.end():at])
    assert len(bodies)==len(names), 'every declared actual EA function must be extracted'
    folder=tmp_path_factory.mktemp('actual-ea-bodies')
    cpp=folder/'ea.cpp'; binary=folder/'ea'
    fixture=Path(__file__).with_name('mql_terminal_fixture.cpp').read_text()
    structure=source[source.index('struct EntryCashMarginCheck'):source.index('bool NativeCheckCurrentEntryCash(')]
    cpp.write_text(fixture.replace('// EXTRACTED_EA_FUNCTIONS',structure+'\n'+'\n'.join(bodies)))
    compiled=subprocess.run(['g++','-std=c++17','-Wall','-Werror','-Wno-sign-compare',str(cpp),'-o',str(binary)],capture_output=True,text=True,timeout=30)
    assert compiled.returncode==0, compiled.stderr
    def run(case):
        return json.loads(subprocess.check_output([str(binary),case],text=True,timeout=15),parse_float=Decimal)
    return run


@pytest.mark.parametrize(('section','field','expected'),[
    ('positions','volume','0.00123456'),('positions','price_open','1.123456789012345'),
    ('positions','profit','0.00001234'),('account','equity','12345.12345678'),
    ('account','balance','12344.12345678'),
])
def test_snapshot_keeps_native_precision(ea,section,field,expected):
    row=ea('snapshot')[section]
    if isinstance(row,list): row=row[0]
    assert abs(Decimal(row[field])-Decimal(expected))<Decimal('1e-12')


def test_failed_position_read_is_unknown_not_empty(ea):
    assert ea('snapshot-missing')['positions'] is None


def test_snapshot_symbol_is_json_escaped(ea):
    assert ea('snapshot-escaped')['positions'][0]['symbol']=='ABC"Q\\R'


def test_entry_resolves_native_deal_position_not_order_ticket(ea):
    r=ea('entry-good')['results'][0]
    assert r['order']==11 and r['position']==42 and r['sl_confirmed'] is True
    assert abs(Decimal(r['volume'])-Decimal('.00123456'))<Decimal('1e-15')
    assert abs(Decimal(r['price'])-Decimal('1.123456789012345'))<Decimal('1e-15')


@pytest.mark.parametrize('case',['entry-unknown-position','entry-wrong-symbol'])
def test_unresolved_position_never_targets_an_order_or_foreign_symbol(ea,case):
    r=ea(case)
    assert len(r['results'])==1 and r['results'][0]['position'] is None
    assert r['results'][0]['sl_confirmed'] is False and r['close_calls']==0


def test_weaker_existing_stop_is_not_confirmed(ea):
    assert ea('entry-weak-stop')['results'][0]['sl_confirmed'] is False


def test_missing_stop_retains_original_fill_without_contradictory_rejection(ea):
    r=ea('entry-no-stop')
    assert len(r['results'])==1 and r['results'][0]['status']=='FILLED'
    assert r['results'][0]['sl_confirmed'] is False


@pytest.mark.parametrize(('case','status'),[
    ('partial-close','PARTIAL'),('unknown-close','UNKNOWN'),('rejected-close','REJECTED'),
    ('entry-partial','PARTIAL'),('entry-unknown','UNKNOWN'),
])
def test_native_finality_is_not_invented(ea,case,status):
    assert ea(case)['results'][0]['status']==status


def test_pending_order_has_no_invented_stop_readback(ea):
    assert ea('entry-pending')['results'][0]['sl_confirmed'] is False


def test_zero_sell_stop_cannot_remove_protection(ea):
    r=ea('zero-sell-stop')
    assert r['results'][0]['ok'] is False and r['modify_calls']==0


def test_modify_bool_does_not_override_native_rejection(ea):
    assert ea('modify-rejected')['results'][0]['ok'] is False


def test_native_modify_ack_without_confirming_readback_stays_unknown(ea):
    assert ea('modify-unobserved')['results'][0]['ok'] is None


def test_confirmed_stop_change_still_works(ea):
    assert ea('modify-good')['results'][0]['ok'] is True


@pytest.mark.parametrize('case',['entry-disconnected','entry-negative-volume','entry-nan-stop','entry-invalid-side'])
def test_native_entry_rechecks_current_permission_and_valid_parameters(ea,case):
    r=ea(case)
    assert r['results'][0]['status']=='REJECTED' and r['entry_calls']==0


@pytest.mark.parametrize('case',['entry-deadline-expired','entry-deadline-subsecond','entry-deadline-delayed',
    'entry-deadline-malformed','entry-deadline-overflow','entry-identity-delayed','entry-permission-delayed'])
def test_actual_ea_entry_binding_and_deadline_survive_native_preparation(ea,case):
    value=ea(case)
    assert value['entry_calls']==0 and value['results'][0]['status']=='REJECTED'


def test_actual_ea_bounded_entry_still_executes_once_and_advertises_its_protocol(ea):
    value=ea('entry-deadline-good')
    assert value['entry_calls']==1 and value['results'][0]['status']=='FILLED'
    assert ea('snapshot')['account']['entry_constraints']=={
        'schema':'van.mt5.ea-entry-constraints/1','explicit_deadline':True,
        'required_op':'ORDER_SEND_EXPIRING','framed_fields':18}


@pytest.mark.parametrize('case',['entry-cash-credit','entry-cash-used','entry-cash-fraction-boundary',
    'entry-cash-after','entry-cash-final','entry-cash-limit-insufficient'])
def test_actual_ea_cash_gate_rejects_before_either_native_entry_effect(ea,case):
    value=ea(case);result=value['results'][0]
    assert value['entry_calls']==0 and value['margin_calls']==1 and result['status']=='REJECTED'
    assert result['reason_code']=='NATIVE_CASH_MARGIN_INSUFFICIENT'
    if case=='entry-cash-final':assert value['post_margin_cash_reads']==2


@pytest.mark.parametrize('case',['entry-cash-missing','entry-cash-nonfinite','entry-cash-units'])
def test_actual_ea_unavailable_margin_never_becomes_zero_cash_requirement(ea,case):
    value=ea(case)
    assert value['entry_calls']==0 and value['results'][0]['reason_code']=='NATIVE_CASH_MARGIN_UNAVAILABLE'


@pytest.mark.parametrize('case',['entry-cash-deadline','entry-cash-permission'])
def test_actual_ea_margin_calculation_cannot_renew_authority(ea,case):
    value=ea(case)
    assert value['margin_calls']==1 and value['entry_calls']==0 and value['results'][0]['status']=='REJECTED'


@pytest.mark.parametrize('case',['entry-cash-zero','entry-cash-sell','entry-cash-limit-good'])
def test_actual_ea_cash_positive_paths_preserve_native_entry_kind(ea,case):
    value=ea(case)
    assert value['entry_calls']==1 and value['margin_calls']==1
    assert value['results'][0]['status']==('ACCEPTED' if case=='entry-cash-limit-good' else 'FILLED')
    assert value['last_margin_side']==(1 if case=='entry-cash-sell' else 0)


def test_actual_ea_protective_controls_still_work_without_entry_cash(ea):
    closed=ea('cash-protective-close');modified=ea('cash-protective-modify')
    assert closed['close_calls']==1 and closed['results'][0]['status']=='FILLED'
    assert modified['modify_calls']==1 and modified['results'][0]['ok'] is True
    assert closed['margin_calls']==modified['margin_calls']==0


@pytest.mark.parametrize('case',['unknown-close','partial-close'])
def test_pull_client_preserves_unconfirmed_native_stop_state(ea,tmp_path,case):
    from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
    q=BridgeQueue(tmp_path/'queue.sqlite')
    try:
        adapter=Mt5PullAdapter(q)
        adapter._await=lambda _:ea(case)['results'][0]
        r=adapter.close('42',None,now_ms=1700000000000,reason='protective')
        assert r.status==('PARTIAL' if case=='partial-close' else 'UNKNOWN')
        assert r.protective_stop_confirmed is False
    finally:
        q.close()


def test_pull_entry_keeps_unresolved_position_absent(ea,tmp_path):
    from vati.execution.base import OrderCommand, StopMode
    from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
    from vati.risk.contracts import Direction, LossModel
    q=BridgeQueue(tmp_path/'queue.sqlite')
    try:
        cmd=OrderCommand('intent','d'*64,'key','mt5_ea','mt5','EURUSD',Direction.LONG,
            'MARKET',Decimal('.00123456'),Decimal('1.123456789012345'),Decimal('1.12'),
            StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
        r=Mt5PullAdapter(q)._entry_receipt(cmd,ea('entry-unknown-position')['results'][0],now_ms=1700000000000)
        assert r.status=='FILLED' and r.filled_qty>0 and r.broker_position_id==''
    finally:
        q.close()


@pytest.mark.parametrize('case',['entry-netting-position','entry-netting-pending'])
def test_native_netting_entry_cannot_change_existing_exposure_or_protection(ea,case):
    r=ea(case)
    assert r['results'][0]['status']=='REJECTED' and r['entry_calls']==0


def test_native_empty_netting_account_can_still_submit_its_first_entry(ea):
    assert ea('entry-netting-empty')['entry_calls']==1


def test_native_pending_order_snapshot_is_explicit_and_precise(ea):
    assert ea('snapshot')['orders']==[]
    order=ea('snapshot-pending')['orders'][0]
    assert order['ticket']==11 and order['symbol']=='EURUSD'
    assert abs(Decimal(order['volume'])-Decimal('.00123456'))<Decimal('1e-15')
    assert abs(Decimal(order['price'])-Decimal('1.123456789012345'))<Decimal('1e-15')


def test_failed_native_pending_order_read_stays_unknown(ea):
    assert ea('snapshot-order-unavailable')['orders'] is None


def test_actual_ea_cash_body_reaches_the_same_native_funding_parser(ea):
    from vati.funding.mt5 import frame_from_poll
    account=ea('snapshot')['account']
    frame=frame_from_poll('controlled-terminal',account,received_ms=1700000000000,nonce='controlled-signed-poll')
    assert frame.movements[0].native_id==9007199254740993
    assert frame.movements[0].operation=='DEAL_TYPE_BALANCE'
    assert abs(frame.movements[0].fee-Decimal('-0.00000013'))<Decimal('1e-22')
    assert frame.credit==200 and frame.net_equity==frame.reported_equity-200
    assert frame.body()['native_time_basis']=='MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED'


@pytest.mark.parametrize('case',['history-unavailable','deal-unavailable','values-unavailable','funds-unavailable',
    'funds-changed','identity-changed','query-expired','nonfinite','bound','history-bound'])
def test_actual_ea_cash_failures_stay_unavailable_while_existing_positions_and_results_survive(ea,case):
    snapshot=ea('snapshot-cash-'+case)
    assert snapshot['account']['funding']['complete'] is False
    assert 'movements' not in snapshot['account']['funding']
    assert len(snapshot['positions'])==1 and snapshot['results']==[]


@pytest.mark.parametrize('case',['empty','trade'])
def test_observed_empty_cash_and_excluded_trade_rows_are_explicit_successful_queries(ea,case):
    funding=ea('snapshot-cash-'+case)['account']['funding']
    assert funding['complete'] is True and funding['movements']==[]
    assert funding['native_from_ms']==0 and funding['native_to_ms']>=funding['native_clock_ms']


def test_native_cash_formatter_does_not_round_a_small_finite_fee_to_zero(ea):
    from vati.funding.mt5 import frame_from_poll
    account=ea('snapshot-cash-tiny-fee')['account']
    frame=frame_from_poll('controlled-terminal',account,received_ms=1700000000000,nonce='controlled-tiny-fee-poll')
    assert frame.movements[0].fee!=0
    assert abs(frame.movements[0].fee-Decimal('-1.2345678901234567e-30'))<Decimal('1e-45')


def test_actual_ea_native_margin_fields_remain_original_decimal_observations(ea):
    from vati.execution.native_margin import mt5_margin
    account=ea('snapshot')['account'];used,free,level=mt5_margin(account)
    assert used==1000 and abs(free-Decimal('11345.12345678'))<Decimal('1e-10')
    assert abs(level-Decimal('1234.512345678'))<Decimal('1e-10')


@pytest.mark.parametrize('case',['unavailable','nonfinite'])
def test_actual_ea_unknown_margin_cannot_be_serialized_as_healthy_zero(ea,case):
    from vati.execution.native_margin import mt5_margin
    account=ea('snapshot-margin-'+case)['account']
    assert mt5_margin(account)==(None,None,None)
    assert account['margin_used'] is None and account['margin_free'] is None


def test_actual_ea_flat_margin_preserves_zero_usage_and_undefined_ratio(ea):
    from vati.execution.native_margin import mt5_margin
    used,free,level=mt5_margin(ea('snapshot-margin-flat')['account'])
    assert used==0 and free>0 and level is None
