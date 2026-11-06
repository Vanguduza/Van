"""A real authority/router ADD creates one child leg of one lifetime family."""
from decimal import Decimal as D

from test_active_trade_e2e import world, _intent, _market_state, SYMBOL, STRATEGY
from vati.lifecycle.scale_policy import Adjustment, PositionAdjustmentProposal
from vati.lifecycle.thesis import ThesisState


def test_actual_add_caller_retains_root_native_quantity_and_shared_family_budget(world):
    now=1_800_000_000_000
    world.state=_market_state(now)
    intent=_intent(now)
    decision=world.authority.evaluate(intent,world._snapshot_for(SYMBOL))
    receipt=world.router.execute(intent,decision,world.mandate,now_ms=now)
    world.lifecycle.record_entry(intent=intent,receipt=receipt,state=world.state,
        modelled_cost_pct=D('.0002'),software_stop=False,decision=decision)
    row=world.lifecycle.entries[intent.trade_intent_id]
    thesis=world.lifecycle.thesis.thesis_for(intent.trade_intent_id)
    half=(decision.approved_risk_pct/2).quantize(D('.00001'))
    proposal=PositionAdjustmentProposal(trade_intent_id=intent.trade_intent_id,
        symbol=SYMBOL,strategy_id=STRATEGY,action=Adjustment.ADD,reasons=('THESIS_STRONGER',),
        rationale='source workflow caller test',thesis_state=ThesisState.STRONGER.value,
        thesis_seal=thesis.seal,delta_risk_pct=half,
        original_approved_risk_pct=decision.approved_risk_pct,risk_after_action_pct=half,
        proposed_ms=now+60000)
    world.lifecycle.execute_add_fn=lambda i,d: world.router.execute(i,d,world.mandate,now_ms=now+60000)
    family=world.lifecycle.families.for_intent(intent.trade_intent_id)
    world.lifecycle._execute_adjustment(proposal=proposal,row=row,intent_id=intent.trade_intent_id,
        thesis=thesis,family=family,mark=D('1.10600'),now_ms=now+60000)
    positions={p.trade_intent_id:p for p in world.adapter.positions()}
    assert len(positions)==2 and family.scale_ins==1
    child_id=next(iid for iid in positions if iid!=intent.trade_intent_id)
    child=world.lifecycle.entries[child_id]
    assert row['quantity']==positions[intent.trade_intent_id].quantity==receipt.filled_qty
    assert child['quantity']==positions[child_id].quantity
    assert child['broker_position_id']!=row['broker_position_id']
    assert child['family_id']==row['family_id']==family.family_id
    assert child['original_approved_risk_pct']==row['original_approved_risk_pct']
    assert child['scale_ins_used']==row['scale_ins_used']==1
    assert family.net_quantity==row['quantity']+child['quantity']
    assert world.lifecycle.families.for_intent(child_id) is family
