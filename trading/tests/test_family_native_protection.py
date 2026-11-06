"""Independent native stops preserve original leg evidence and one family fold."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_family_durable_projection import recorded_scale
from vati.core import Ledger, EventKind
from vati.execution.native_protection import observe_paper_native_protection, original_native_protection
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family import FamilyRegistry
from vati.lifecycle.family_execution import reduce_original_family_receipts
from vati.lifecycle.family_outcome import publish_family_outcome


def test_one_native_stop_leaves_other_original_leg_open_and_each_close_reduces_once(tmp_path):
    with closing(Ledger(tmp_path/'stops.sqlite')) as ledger:
        life,adapter,root,child,entry,added=recorded_scale(ledger,netted=False)
        family=life.families.for_intent(root.trade_intent_id)
        adapter.modify_stop(added.broker_position_id,D('1.105'),now_ms=3500)
        native=adapter.mark('EURUSD',D('1.104'),D('1.104'),now_ms=4000)
        assert len(native)==1 and native[0].trade_intent_id==child.trade_intent_id
        proof=observe_paper_native_protection(life.router,adapter,native[0],now_ms=4000)
        assert observe_paper_native_protection(life.router,adapter,native[0],now_ms=4001).hash==proof.hash
        snapshot=reduce_original_family_receipts(life,family.family_id,now_ms=4001)
        assert snapshot.known and family.net_quantity==D('.06') and len(adapter.positions())==1
        assert publish_family_outcome(life,family.family_id,reason='NATIVE_STOP',now_ms=4001) is None
        assert not life.reviews
        count=len(family.members)
        reduce_original_family_receipts(life,family.family_id,now_ms=4002)
        assert len(family.members)==count and family.net_quantity==D('.06')
        native=adapter.mark('EURUSD',D('1.08'),D('1.08'),now_ms=5000)
        assert len(native)==1 and native[0].trade_intent_id==root.trade_intent_id
        observe_paper_native_protection(life.router,adapter,native[0],now_ms=5000)
        outcome=publish_family_outcome(life,family.family_id,reason='NATIVE_STOP',now_ms=5001)
        assert family.net_quantity==0 and not adapter.positions()
        # This legacy fixture has no original sealed risk decision: no invented R.
        assert outcome.kind is EventKind.SESSION
        assert outcome.payload['state']=='CLOSED_ORIGINAL_RISK_UNIT_UNKNOWN'
        assert outcome.payload['child_learning_trials']==0 and not life.reviews
        history=NativePositionHistory(ledger,account_alias='acct',venue='paper')
        restored=FamilyRegistry().restore(history,family_id=family.family_id,
            trade_intent_id=root.trade_intent_id,symbol='EURUSD',direction=root.direction,
            position_id=entry.broker_position_id)
        assert restored.net_quantity==0 and len(restored.members)==len(family.members)


@pytest.mark.parametrize('damage',['foreign-intent','foreign-position','quantity','not-native-reason'])
def test_native_stop_observer_refuses_unbound_or_changed_receipts(tmp_path,damage):
    with closing(Ledger(tmp_path/'stops.sqlite')) as ledger:
        life,adapter,root,child,entry,added=recorded_scale(ledger,netted=False)
        receipt=adapter.mark('EURUSD',D('1.08'),D('1.08'),now_ms=4000)[0]
        if damage=='foreign-intent':receipt=replace(receipt,trade_intent_id='manual')
        elif damage=='foreign-position':receipt=replace(receipt,broker_position_id='foreign')
        elif damage=='quantity':receipt=replace(receipt,filled_qty=receipt.filled_qty+D('.01'))
        else:receipt=replace(receipt,reject_reason='OWNER_ASSERTION')
        receipt=replace(receipt,receipt_hash='').sealed()
        before=ledger.count()
        with pytest.raises(ValueError):observe_paper_native_protection(life.router,adapter,receipt,now_ms=4000)
        assert ledger.count()==before
