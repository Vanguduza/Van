"""Actual native control producer retains data without issuing a new grant."""
from dataclasses import replace
from types import SimpleNamespace

from conftest import NOW
from test_native_risk_history_inputs import native_facts
from vati.app.runtime_control_actor import _native_control_metadata
from vati.core import EventKind
from vati.execution.paper import PaperAdapter


def test_real_mt5_control_producer_preserves_original_query_and_no_order_effect(tmp_path, eurusd):
    ledger, adapter, account, captured, _ = native_facts(tmp_path, eurusd)
    c=SimpleNamespace(ledger=ledger,adapter=adapter)
    before=ledger.count()
    value=_native_control_metadata(c,account,NOW*1000)
    context=value['native_account_context']
    assert context['account_alias']==account.account_alias
    assert context['source_query_ref']==captured['query_ref']
    assert context['execution_authority'] is context['risk_capital_qualified'] is False
    assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0
    assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0


def test_missing_native_source_is_visible_and_cannot_be_filled_from_current_profile(tmp_path,eurusd):
    ledger,adapter,account,_,_=native_facts(tmp_path,eurusd)
    c=SimpleNamespace(ledger=ledger,adapter=adapter)
    value=_native_control_metadata(c,replace(account,funding_mark=None),NOW*1000)
    assert value=={'native_history_source_state':'UNAVAILABLE'}
    assert 'native_account_context' not in value


def test_non_native_control_payload_keeps_the_original_contract(tmp_path,eurusd):
    ledger,_,account,_,_=native_facts(tmp_path,eurusd)
    assert _native_control_metadata(SimpleNamespace(ledger=ledger,adapter=PaperAdapter()),account,NOW*1000)=={}
