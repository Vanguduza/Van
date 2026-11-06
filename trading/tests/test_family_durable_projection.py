"""Family publication, original evidence and exact consumer regression cases."""
from dataclasses import replace
from contextlib import closing
from decimal import Decimal as D, localcontext, Inexact, Rounded
import pytest
from vati.core import Ledger, EventKind, make_event
from vati.lifecycle.family import FamilyRegistry, FamilyMember, MemberRole, FamilyError, FamilyState
from vati.lifecycle.envelope import EnvelopeCalculator, GuaranteedExitCertificate
from vati.lifecycle.expansion import ProfitExpansionEngine
from vati.lifecycle.preservation import PreservationEngine
from vati.risk.contracts import Direction
from test_family_original_accounting import after_partial, recorded_paper_partial


def opened(ledger):
    reg=FamilyRegistry(ledger=ledger)
    family=reg.open_family(family_id='f',account_alias='acct',symbol='EURUSD',direction=Direction.LONG,
        root=FamilyMember('root',MemberRole.ROOT,D(1),D(1),1000,trade_intent_id='root',stop=D('.5')),now_ms=1000)
    return reg,family


@pytest.mark.parametrize('operation',['add','stop','reconcile'])
def test_failed_publication_preserves_members_and_fences_risk(tmp_path,monkeypatch,operation):
    with closing(Ledger(tmp_path/'family.sqlite')) as ledger:
        reg,fam=opened(ledger);members=[m.body() for m in fam.members];stop=fam.current_stop
        monkeypatch.setattr(ledger,'append',lambda event: (_ for _ in ()).throw(OSError('source failure')))
        with pytest.raises(FamilyError):
            if operation=='add':reg.apply('f',FamilyMember('add',MemberRole.SCALE_IN,D(1),D(2),2000),now_ms=2000)
            elif operation=='stop':reg.tighten_stop('f',D('.7'),now_ms=2000)
            else:reg.reconcile('f',venue_quantity=D('.5'),now_ms=2000)
        assert [m.body() for m in fam.members]==members and fam.current_stop==stop
        assert fam.state is FamilyState.DIVERGED and not fam.admits_new_risk
        assert ledger.count(EventKind.POSITION_FAMILY)==1


def test_lost_ack_reads_original_committed_family_and_replay_does_not_add_twice(tmp_path,monkeypatch):
    with closing(Ledger(tmp_path/'family.sqlite')) as ledger:
        reg,fam=opened(ledger);append=ledger.append
        def lost_ack(event):
            append(event)
            raise OSError('committed but reply lost')
        monkeypatch.setattr(ledger,'append',lost_ack)
        member=FamilyMember('add',MemberRole.SCALE_IN,D(1),D(2),2000)
        reg.apply('f',member,now_ms=2000)
        assert fam.gross_added==D(2) and fam.scale_ins==1
        reg.apply('f',member,now_ms=2000)
        assert fam.gross_added==D(2) and fam.scale_ins==1 and ledger.verify_chain()[0]


def test_failed_open_never_publishes_root_or_intent(tmp_path,monkeypatch):
    with closing(Ledger(tmp_path/'family.sqlite')) as ledger:
        reg=FamilyRegistry(ledger=ledger)
        monkeypatch.setattr(ledger,'append',lambda event: (_ for _ in ()).throw(OSError('source failure')))
        with pytest.raises(FamilyError):
            reg.open_family(family_id='f',account_alias='acct',symbol='EURUSD',direction=Direction.LONG,
                root=FamilyMember('root',MemberRole.ROOT,D(1),D(1),1000,trade_intent_id='root'),now_ms=1000)
        assert len(reg)==0 and reg.for_intent('root') is None


def test_rounded_average_cannot_authorise_a_stop_below_exact_entry():
    reg=FamilyRegistry();fam=reg.open_family(family_id='f',account_alias='acct',symbol='EURUSD',direction=Direction.LONG,
        root=FamilyMember('root',MemberRole.ROOT,D(1),D(1),1000,stop=D('.5')),now_ms=1000)
    reg.apply('f',FamilyMember('add',MemberRole.SCALE_IN,D(2),D('1.5'),2000),now_ms=2000)
    fam.current_stop=fam.average_entry
    assert not ProfitExpansionEngine._stop_secured(fam)


def test_actual_envelope_and_account_verdict_do_not_use_ambient_precision():
    fam=after_partial();calculator=EnvelopeCalculator()
    expected=calculator.compute(fam,mark=D(130),value_per_price_unit=D(1),equity=D(10000),now_ms=4000)
    with localcontext() as ctx:
        ctx.prec=2;ctx.traps[Inexact]=ctx.traps[Rounded]=True;flags=dict(ctx.flags)
        actual=calculator.compute(fam,mark=D(130),value_per_price_unit=D(1),equity=D(10000),now_ms=4000)
        action=PreservationEngine().account_verdict([actual],equity=D(10000),now_ms=4000)
        assert actual.body()==expected.body() and not action.blocks_new_risk
        assert dict(ctx.flags)==flags


@pytest.mark.parametrize('damage',['members','account','symbol','direction','producer'])
def test_new_snapshot_cannot_rewrite_original_family_or_scope(tmp_path,damage):
    from test_account_lifecycle import _lifecycle
    with closing(Ledger(tmp_path/'family.sqlite')) as ledger:
        life,adapter,cmd,entry=recorded_paper_partial(ledger)
        prior=list(ledger.iter(EventKind.POSITION_FAMILY))[-1];body=dict(prior.payload)
        producer=prior.producer
        if damage=='members':body['members']=body['members'][:1]
        elif damage=='account':body['account_alias']='other'
        elif damage=='symbol':body['symbol']='GBPUSD'
        elif damage=='direction':body['direction']='SHORT'
        else:producer='unrelated-producer'
        ledger.append(make_event(EventKind.POSITION_FAMILY,producer,body,event_time_ms=3000,received_time_ms=3000,
            correlation_id=prior.correlation_id))
        cold=_lifecycle(ledger,adapter);restored,unresolved=cold.recover_from_venue()
        assert not restored and unresolved==(cmd.trade_intent_id,)
        assert cold.protection.stop_of(entry.broker_position_id)==cmd.protective_stop
        assert cold.preservation_blocks_new_risk


def recorded_scale(ledger, *, netted):
    """Real Paper command/receipt history, with a declared netting source peer."""
    from dataclasses import asdict
    from test_account_lifecycle import _append_command
    from vati.execution.paper import PaperAdapter
    life,adapter,root,entry=recorded_paper_partial(ledger)
    child=replace(root,trade_intent_id='family-child',idempotency_key='family-child-idem',
        quantity=D('.05'),entry_price=D('1.11'),decision_hash='b'*64,command_hash='').sealed()
    ledger.append(make_event(EventKind.RISK_DECISION,'vati-account-lifecycle',
        {'parent_trade_intent_id':root.trade_intent_id,'inputs':{'intent':{'decision_hash':child.decision_hash}}},
        event_time_ms=3000,received_time_ms=3000,correlation_id=child.trade_intent_id))
    _append_command(ledger,child,now=3000)
    receipt=adapter.submit(child,now_ms=3000)
    assert receipt.status=='FILLED'
    if netted:
        # This peer explicitly models the single-position native convention;
        # distinct-position Paper behavior remains the hedged case below.
        original=adapter._positions[entry.broker_position_id]
        additional=adapter._positions.pop(receipt.broker_position_id)
        original['entry']=(original['entry']*original['qty']+additional['entry']*additional['qty'])/(original['qty']+additional['qty'])
        original['qty']+=additional['qty']
        receipt=replace(receipt,broker_position_id=entry.broker_position_id,receipt_hash='').sealed()
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',asdict(receipt),
        event_time_ms=3000,received_time_ms=3000,correlation_id=child.trade_intent_id))
    family=life.families.for_intent(root.trade_intent_id)
    life.families.apply(family.family_id,FamilyMember('original-child',MemberRole.SCALE_IN,
        receipt.filled_qty,receipt.average_fill,3000,trade_intent_id=child.trade_intent_id),now_ms=3000)
    return life,adapter,root,child,entry,receipt


def test_netted_native_quantity_above_root_request_recovers_verified_original_family(tmp_path):
    from test_account_lifecycle import _lifecycle
    with closing(Ledger(tmp_path/'netted.sqlite')) as ledger:
        life,adapter,root,child,entry,receipt=recorded_scale(ledger,netted=True)
        assert adapter.positions()[0].quantity > root.quantity
        with closing(Ledger(ledger.path)) as cold:
            restored_life=_lifecycle(cold,adapter);before=cold.count()
            assert restored_life.recover_from_venue()==((root.trade_intent_id,),())
            family=restored_life.families.for_intent(root.trade_intent_id)
            assert family is restored_life.families.for_intent(child.trade_intent_id)
            assert family.net_quantity==D('.11') and family.gross_added==D('.15') and family.scale_ins==1
            assert restored_life.entries[root.trade_intent_id]['scale_ins_used']==1
            assert restored_life.entries[root.trade_intent_id]['family_history_known']
            assert not restored_life.preservation_blocks_new_risk and cold.count()==before


def test_actual_paper_hedged_members_keep_one_lifetime_budget_and_each_native_stop(tmp_path):
    from test_account_lifecycle import _lifecycle
    with closing(Ledger(tmp_path/'hedged.sqlite')) as ledger:
        life,adapter,root,child,entry,receipt=recorded_scale(ledger,netted=False)
        assert len(adapter.positions())==2
        with closing(Ledger(ledger.path)) as cold:
            restored_life=_lifecycle(cold,adapter);before=cold.count();seq=adapter._seq
            assert restored_life.recover_from_venue()==(tuple(sorted([root.trade_intent_id,child.trade_intent_id])),())
            family=restored_life.families.for_intent(root.trade_intent_id)
            assert family is restored_life.families.for_intent(child.trade_intent_id)
            assert family.net_quantity==D('.11') and family.gross_added==D('.15') and family.scale_ins==1
            for command,fill in [(root,entry),(child,receipt)]:
                row=restored_life.entries[command.trade_intent_id]
                assert row['scale_ins_used']==1 and row['family_history_known']
                assert row['family_execution_available'] is False
                assert restored_life.protection.stop_of(fill.broker_position_id)==command.protective_stop
            assert restored_life.preservation_blocks_new_risk
            # Recovery may materialise the child's previously absent TCA; the
            # held family supervisor must dispatch no aggregate action.
            after_recovery=cold.count()
            restored_life._supervise_open_families('EURUSD',D('1.2'),D('1.21'),now_ms=4000)
            assert adapter._seq==seq and cold.count()==after_recovery
            assert restored_life.preservation_blocks_new_risk


def test_legacy_current_position_restores_protection_but_cannot_supply_a_lifetime_budget(tmp_path):
    from test_account_lifecycle import _lifecycle,_command,_append_command
    from vati.execution.paper import PaperAdapter
    with closing(Ledger(tmp_path/'legacy.sqlite')) as ledger:
        adapter=PaperAdapter(venue='paper',account_alias='acct',spread=D(0),slippage=D(0))
        command=_command('legacy-family');_append_command(ledger,command,now=1000)
        receipt=adapter.submit(command,now_ms=1000)
        adapter._positions[receipt.broker_position_id]['qty']=D('.06')
        life=_lifecycle(ledger,adapter)
        assert life.recover_from_venue()==((command.trade_intent_id,),())
        assert life.families.for_intent(command.trade_intent_id) is None
        assert life.entries[command.trade_intent_id]['family_history_known'] is False
        assert life.preservation_blocks_new_risk
        assert life.protection.stop_of(receipt.broker_position_id)==command.protective_stop


def test_closing_one_held_hedged_position_does_not_close_the_other_family_members(tmp_path):
    from test_account_lifecycle import _lifecycle
    with closing(Ledger(tmp_path/'hedged-close.sqlite')) as ledger:
        life,adapter,root,child,entry,child_receipt=recorded_scale(ledger,netted=False)
        recovered=_lifecycle(ledger,adapter);recovered.recover_from_venue()
        family=recovered.families.for_intent(root.trade_intent_id)
        original_members=[member.body() for member in family.members]
        closed=recovered.router.apply_preservation('paper',position_id=entry.broker_position_id,
            trade_intent_id=root.trade_intent_id,action='FULL_CLOSE',quantity=None,now_ms=4000,
            reason='SOURCE_NATIVE_PROTECTIVE_CLOSE')
        assert closed.filled_qty==D('.06')
        recovered._on_close(root.trade_intent_id,closed.average_fill,'SOURCE_NATIVE_PROTECTIVE_CLOSE',4000)
        assert [position.trade_intent_id for position in adapter.positions()]==[child.trade_intent_id]
        assert family.gross_added==D('.15') and family.scale_ins==1
        assert [member.body() for member in family.members]==original_members
        assert family.state is FamilyState.DIVERGED and recovered.preservation_blocks_new_risk


@pytest.mark.parametrize('damage',['account','malformed_member','malformed_root_id'])
def test_failed_second_recovery_cannot_lose_history_hold_during_actual_supervision(tmp_path,damage):
    from test_account_lifecycle import _lifecycle
    with closing(Ledger(tmp_path/'repeat-recovery.sqlite')) as ledger:
        _,adapter,command,entry=recorded_paper_partial(ledger)
        life=_lifecycle(ledger,adapter)
        assert life.recover_from_venue()==((command.trade_intent_id,),())
        family=life.families.for_intent(command.trade_intent_id)
        payload=family.body()
        if damage=='account':payload['account_alias']='foreign'
        elif damage=='malformed_member':payload['members']=['malformed',{'trade_intent_id':command.trade_intent_id}]
        else:payload['members'][0]['trade_intent_id']=['malformed-root']
        ledger.append(make_event(EventKind.POSITION_FAMILY,'vati-position-family',payload,
            event_time_ms=3000,received_time_ms=3000,correlation_id=family.family_id))
        assert life.recover_from_venue()==((),(command.trade_intent_id,))
        assert life.preservation_blocks_new_risk and family.state is FamilyState.DIVERGED
        life._supervise_open_families('EURUSD',D('1.1001'),D('1.1002'),now_ms=4000)
        assert life.preservation_blocks_new_risk and not family.admits_new_risk
        assert life.protection.stop_of(entry.broker_position_id)==command.protective_stop


@pytest.mark.parametrize('equity',['700000','900000','1100000'])
def test_expansion_requested_headroom_never_exceeds_exact_policy_remainder(equity):
    from fractions import Fraction
    from test_rev51_expansion import _evaluate,_health,CONSERVATIVE
    health=_health()
    with localcontext() as ctx:
        ctx.prec=2;ctx.traps[Inexact]=ctx.traps[Rounded]=True;flags=dict(ctx.flags)
        proposal=_evaluate(health=health,equity=equity)
        assert proposal.proposed and proposal.would_propose and not proposal.is_candidate
        assert Fraction(proposal.requested_risk_pct) <= Fraction(CONSERVATIVE.max_family_risk_pct)-Fraction(1500)/Fraction(D(equity))
        assert dict(ctx.flags)==flags


def test_breakeven_stop_report_rounds_toward_protection_not_below_exact_basis():
    from fractions import Fraction
    from test_rev51_expansion import _health
    reg=FamilyRegistry();fam=reg.open_family(family_id='f',account_alias='acct',symbol='EURUSD',direction=Direction.LONG,
        root=FamilyMember('root',MemberRole.ROOT,D(1),D(1),1000,stop=D('.5')),now_ms=1000)
    reg.apply('f',FamilyMember('add',MemberRole.SCALE_IN,D(2),D('1.5'),2000),now_ms=2000)
    stop,reason=PreservationEngine()._tighten_to(fam,_health(),D(2))
    assert reason=='BREAKEVEN_REACHED' and Fraction(stop)>=Fraction(4,3)
