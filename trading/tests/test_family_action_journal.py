"""Exact original family targets survive restart and never resend implicitly."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal as D

import pytest

from test_family_durable_projection import recorded_scale
from test_family_native_action_contract import BINDING
from vati.core import Ledger, EventKind
from vati.execution.recovery_scope import NativePositionHistory
from vati.execution.router import ExitInFlight
from vati.lifecycle.family_actions import FamilyPolicy, FamilyActionError, plan_reduction
from vati.lifecycle.family_action_journal import FamilyActionJournal, target_ref
from vati.lifecycle.family_membership import original_native_snapshot


def prepared(ledger):
    life,adapter,root,child,entry,added = recorded_scale(ledger,netted=False)
    family = life.families.for_intent(root.trade_intent_id)
    history = NativePositionHistory(ledger, account_alias=adapter.account_alias, venue='paper')
    snapshot = original_native_snapshot(history,family,adapter)
    plan = plan_reduction(snapshot,policy=FamilyPolicy(),action='FULL_CLOSE',authority_refs=BINDING)
    action = FamilyActionJournal(ledger).prepare(plan,action_key='original-preservation-decision',now_ms=4000)
    return life,adapter,plan,action


def send(life,action,target,now=4100):
    return life.router.apply_preservation('paper',position_id=target['position_id'],
        trade_intent_id=target['trade_intent_id'],action=target['action'],now_ms=now,
        family_action_ref=action.hash,family_target_ref=target_ref(action.hash,target))


def test_prepared_shadow_plan_is_data_and_cannot_rewrite_original_targets(tmp_path):
    with closing(Ledger(tmp_path/'action.sqlite')) as ledger:
        life,adapter,plan,action = prepared(ledger)
        assert len(adapter.positions()) == 2
        assert action.payload['execution_authority'] is False
        journal=FamilyActionJournal(ledger)
        assert journal.prepare(plan,action_key='original-preservation-decision',now_ms=5000).hash == action.hash
        changed=replace(plan,reason='later quantities must not replan the original request')
        with pytest.raises(FamilyActionError,match='cannot be replanned'):
            journal.prepare(changed,action_key='original-preservation-decision',now_ms=5000)
        with closing(Ledger(ledger.path)) as cold:
            assert FamilyActionJournal(cold).find(plan.snapshot.family_id,'original-preservation-decision').hash == action.hash


def test_each_target_joins_its_original_request_and_receipt_after_restart(tmp_path):
    with closing(Ledger(tmp_path/'action.sqlite')) as ledger:
        life,adapter,plan,action=prepared(ledger)
        target=action.payload['plan']['targets'][0]
        receipt=send(life,action,target)
        assert receipt.status == 'FILLED'
        remaining=[p.position_id for p in adapter.positions()]
        with pytest.raises(ExitInFlight,match='already attempted'):
            send(life,action,target,now=4200)
        assert [p.position_id for p in adapter.positions()] == remaining
        with closing(Ledger(ledger.path)) as cold:
            attempt,outcome=FamilyActionJournal(cold).target_outcome(action,target)
            assert attempt.payload['family_target_ref'] == target_ref(action.hash,target)
            assert outcome.payload['state'] == 'CONFIRMED'
            original=next(e for e in cold.iter(EventKind.EXECUTION_RECEIPT)
                if e.hash == outcome.payload['receipt_event_ref'])
            assert original.payload['receipt_hash'] == receipt.receipt_hash
            assert original.payload['exit_request_ref'] == attempt.hash


def test_foreign_or_changed_target_is_refused_before_transport(tmp_path):
    with closing(Ledger(tmp_path/'action.sqlite')) as ledger:
        life,adapter,plan,action=prepared(ledger)
        target=dict(action.payload['plan']['targets'][0],position_id='manual-position')
        with pytest.raises(ValueError,match='original family leg target'):
            send(life,action,target)
        assert len(adapter.positions()) == 2
        assert FamilyActionJournal(ledger).target_attempt(action,action.payload['plan']['targets'][0]) is None


def test_unknown_original_target_stays_fenced_and_other_leg_can_still_close(tmp_path,monkeypatch):
    with closing(Ledger(tmp_path/'action.sqlite')) as ledger:
        life,adapter,plan,action=prepared(ledger)
        first,second=action.payload['plan']['targets']
        close=adapter.close
        def uncertain(pid,*args,**kwargs):
            if pid == first['position_id']:
                raise OSError('native reply unavailable')
            return close(pid,*args,**kwargs)
        monkeypatch.setattr(adapter,'close',uncertain)
        with pytest.raises(OSError,match='native reply unavailable'):
            send(life,action,first)
        with pytest.raises(ExitInFlight,match='already attempted'):
            send(life,action,first,now=4200)
        receipt=send(life,action,second,now=4300)
        assert receipt.status == 'FILLED'
        attempt,outcome=FamilyActionJournal(ledger).target_outcome(action,first)
        assert attempt is not None and outcome is None
        assert len(adapter.positions()) == 1
