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
           'SnapshotJson','PushResult','ExecOrderSend','ExecModifySl','ExecClose'}
    bodies=[]
    for match in re.finditer(r'^(?:string|void|bool|ulong) (\w+)\([^\n]*\)\s*\{',source,re.M):
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
        bodies.append(source[match.start():at])
    assert len(bodies)>=6
    folder=tmp_path_factory.mktemp('actual-ea-bodies')
    cpp=folder/'ea.cpp'; binary=folder/'ea'
    fixture=Path(__file__).with_name('mql_terminal_fixture.cpp').read_text()
    cpp.write_text(fixture.replace('// EXTRACTED_EA_FUNCTIONS','\n'.join(bodies)))
    compiled=subprocess.run(['g++','-std=c++17','-Wall','-Werror','-Wno-sign-compare',str(cpp),'-o',str(binary)],capture_output=True,text=True)
    assert compiled.returncode==0, compiled.stderr
    def run(case):
        return json.loads(subprocess.check_output([str(binary),case],text=True),parse_float=Decimal)
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
