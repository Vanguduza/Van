"""Actual original journals -> exact closing-balance observation, not settlement."""
from decimal import Decimal as D,localcontext
from dataclasses import replace
import pytest

from test_native_balance_reconciliation import mark,snapshot,observe,closed
from vati.core import Ledger,EventKind
from vati.core.units import Money,balanced_postings


def originals(ledger):
    before=snapshot(ledger,mark(1000))
    scope=observe(ledger,deals=(closed(),))
    event=next(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT))
    return before,event,scope


def test_original_native_balance_delta_does_not_guess_commission_sign_or_future_fees(tmp_path):
    from vati.funding.close_postings import FinancialCloseMovement
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before,event,scope=originals(ledger)
        movement=FinancialCloseMovement(event,1,before,recorded_at_ms=7000)
        body=movement.body()
        assert Money.from_body(body['amount']).decimal==D('10')
        assert body['scope_hash']==scope and body['source_statement_ref']==event.hash
        assert body['balance_anchor']['record_ref']==before.hash
        assert body['native_balance_version_before']==1 and body['native_balance_version_after']==2
        assert body['raw_fee_observations']['close']['commission']=='-1'
        assert body['raw_fee_observations']['close']['pnl_conversion_fee'] is None
        assert body['fee_allocation_state']=='UNQUALIFIED_NOT_INFERRED_FROM_BALANCE_DELTA'
        assert body['settlement_qualification']=='NOT_ISSUED'
        assert body['risk_capital_qualified'] is body['trade_alpha_claimed'] is body['execution_authority'] is False
        assert balanced_postings(movement.postings)==movement.postings
        assert sum(p.amount.fraction for p in movement.postings)==0
        body['raw_fee_observations']['close']['commission']='0'
        assert movement.body()['raw_fee_observations']['close']['commission']=='-1'
    finally:ledger.close()


@pytest.mark.parametrize('damage',['gap','wrong_scope','future_availability'])
def test_unbound_balance_baseline_cannot_supply_a_closing_cash_delta(tmp_path,damage):
    from vati.funding.close_postings import FinancialCloseMovement
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before,event,scope=originals(ledger);at=7000
        if damage=='gap':before=snapshot(ledger,mark(1000,version=0))
        elif damage=='wrong_scope':before=snapshot(ledger,replace(mark(1000),native_account_id=54321))
        else:at=5999
        with pytest.raises(ValueError):FinancialCloseMovement(event,1,before,recorded_at_ms=at)
    finally:ledger.close()


def test_existing_financial_owner_publishes_and_independently_reads_original_close_observation(tmp_path):
    from vati.funding.movement_journal import FinancialMovementBook
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before,event,scope=originals(ledger);book=FinancialMovementBook(ledger,clock=lambda:7000)
        receipt=book.publish_close('original-close',scope_hash=scope,native_id=1,
            statement_ref=event.hash,balance_anchor_ref=before.hash)
        assert receipt==book.lookup('original-close')
        original=book.inspect('original-close')
        assert original['current_original_source_verified'] is True
        assert Money.from_body(original['movement']['amount']).decimal==D('10')
        assert original['movement']['source_kind']=='CTRADER_NATIVE_CLOSE'
        assert original['publication']['risk_capital_qualified'] is original['publication']['execution_authority'] is False
        count=ledger.count()
        assert book.publish_close('original-close',scope_hash=scope,native_id=1,
            statement_ref=event.hash,balance_anchor_ref=before.hash)==receipt
        assert ledger.count()==count and ledger.count(EventKind.FINANCIAL_MOVEMENT)==1
    finally:ledger.close()


@pytest.mark.parametrize('kind',['cash','close'])
def test_cash_or_prior_close_can_anchor_the_next_exact_native_balance_version(tmp_path,kind):
    from vati.funding.close_postings import FinancialCloseMovement
    from test_native_balance_reconciliation import cash
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before=snapshot(ledger,mark(1000))
        next_close=closed(balance='115',version=3,at=2500)
        next_close=replace(next_close,native_id=2)
        if kind=='cash':
            scope=observe(ledger,cash=(cash(delta='10',balance='110',version=2),),deals=(next_close,))
            anchor=next(ledger.iter(EventKind.FUNDING_STATEMENT));anchor_id=7
        else:
            scope=observe(ledger,deals=(closed(),next_close))
            anchor=next(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT));anchor_id=1
        source=next(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT))
        with localcontext() as context:
            context.prec=1
            movement=FinancialCloseMovement(source,2,anchor,anchor_native_id=anchor_id,recorded_at_ms=7000)
        assert Money.from_body(movement.body()['amount']).decimal==D('5.00')
        assert movement.body()['balance_anchor']['native_id']==str(anchor_id)
        assert movement.body()['scope_hash']==scope
    finally:ledger.close()


@pytest.mark.parametrize('collision',['two_closes','cash_and_close','contradictory_mark'])
def test_current_native_version_ambiguity_blocks_new_close_postings(tmp_path,collision):
    from vati.funding.movement_journal import FinancialMovementBook
    from test_native_balance_reconciliation import cash
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before=snapshot(ledger,mark(1000));deals=(closed(),);cash_rows=()
        if collision=='two_closes':deals+=(replace(closed(),native_id=2),)
        elif collision=='cash_and_close':cash_rows=(cash(delta='10',balance='110',version=2),)
        else:snapshot(ledger,mark(1100,balance='101',equity='101',version=1))
        scope=observe(ledger,cash=cash_rows,deals=deals)
        event=next(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT));count=ledger.count()
        with pytest.raises(ValueError,match='NATIVE_BALANCE_VERSION_CONFLICT'):
            FinancialMovementBook(ledger,clock=lambda:7000).publish_close('ambiguous-close',scope_hash=scope,
                native_id=1,statement_ref=event.hash,balance_anchor_ref=before.hash)
        assert ledger.count()==count and ledger.count(EventKind.FINANCIAL_MOVEMENT)==0
        view=FinancialMovementBook(ledger).projection(scope)
        assert view['state']=='CONFLICT' and view['reason']=='FINANCIAL_NATIVE_BALANCE_VERSION_CONFLICT'
        assert 'unresolved_closes' not in view,'conflicting original versions are not missing balance anchors'
    finally:ledger.close()


def test_automatic_materialization_exposes_original_close_on_the_existing_read_model(tmp_path):
    from vati.funding.movement_journal import FinancialMovementBook
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before,event,scope=originals(ledger);book=FinancialMovementBook(ledger,clock=lambda:7000)
        result=book.materialize(scope)
        assert result['posted_count']==result['original_movement_count']==1
        assert result['pending_count']==0 and result['current_original_source_verified'] is True
        assert result['movements'][0]['movement']['source_kind']=='CTRADER_NATIVE_CLOSE'
        assert result['movements'][0]['publication']['execution_authority'] is False
        count=ledger.count()
        assert book.materialize(scope)==result and ledger.count()==count
    finally:ledger.close()


def test_bounded_native_close_catch_up_uses_prior_original_close_without_reposting(tmp_path):
    from vati.funding.movement_journal import FinancialMovementBook
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before=snapshot(ledger,mark(1000))
        second=replace(closed(balance='115',version=3,at=2500),native_id=2)
        scope=observe(ledger,deals=(closed(),second));book=FinancialMovementBook(ledger,clock=lambda:7000)
        first=book.materialize(scope,max_batch=1)
        assert first['posted_count']==1 and first['pending_count']==1
        final=book.materialize(scope,max_batch=1)
        assert final['posted_count']==2 and final['pending_count']==0
        assert sum(Money.from_body(r['movement']['amount']).fraction for r in final['movements'])==15
        assert final['movements'][1]['movement']['balance_anchor']['native_id']=='1'
        assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==2
    finally:ledger.close()


def test_cash_and_deal_id_namespaces_do_not_suppress_each_others_original_posting(tmp_path):
    from vati.funding.movement_journal import FinancialMovementBook
    from test_native_balance_reconciliation import cash
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        snapshot(ledger,mark(1000))
        close=replace(closed(balance='115',version=3,at=2500),native_id=7)
        scope=observe(ledger,cash=(cash(delta='10',balance='110',version=2),),deals=(close,))
        result=FinancialMovementBook(ledger,clock=lambda:7000).materialize(scope)
        assert result['posted_count']==result['original_movement_count']==2 and result['pending_count']==0
        assert {r['movement']['source_kind'] for r in result['movements']}=={'CTRADER_NATIVE_CASH','CTRADER_NATIVE_CLOSE'}
        assert {r['movement']['native_id'] for r in result['movements']}=={'7'}
        assert sum(Money.from_body(r['movement']['amount']).fraction for r in result['movements'])==15
        assert len({r['movement']['movement_id'] for r in result['movements']})==2
    finally:ledger.close()


def test_missing_original_balance_anchor_is_pending_without_assuming_zero_cash(tmp_path):
    from vati.funding.movement_journal import FinancialMovementBook
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        scope=observe(ledger,deals=(closed(),));before=ledger.count()
        result=FinancialMovementBook(ledger,clock=lambda:7000).materialize(scope)
        assert result['state']=='PENDING' and result['posted_count']==0 and result['pending_count']==1
        assert result['unresolved_closes']==[{'native_id':'1','reason':'FINANCIAL_ORIGINAL_BALANCE_ANCHOR_UNAVAILABLE'}]
        assert ledger.count()==before and ledger.count(EventKind.FINANCIAL_MOVEMENT)==0
    finally:ledger.close()


def test_late_conflicting_native_fee_keeps_original_posting_but_refuses_current_use(tmp_path):
    from vati.funding.movement_journal import FinancialMovementBook
    ledger=Ledger(tmp_path/'facts.sqlite')
    try:
        before,event,scope=originals(ledger);book=FinancialMovementBook(ledger,clock=lambda:7000)
        receipt=book.publish_close('original-close',scope_hash=scope,native_id=1,
            statement_ref=event.hash,balance_anchor_ref=before.hash)
        amended=replace(closed(),commission=D('-2'))
        observe(ledger,deals=(amended,))
        count=ledger.count()
        assert book.lookup('original-close')==receipt
        assert book.inspect('original-close')['current_original_source_verified'] is False
        result=book.materialize(scope)
        assert result['state']=='CONFLICT' and result['posted_count']==1
        assert result['movements'][0]['movement']['raw_fee_observations']['deal_commission']=='-1'
        assert ledger.count()==count and ledger.count(EventKind.FINANCIAL_MOVEMENT)==1
    finally:ledger.close()


def test_actual_native_adapter_and_funding_capture_publish_the_new_close_in_the_same_sweep(tmp_path):
    from test_native_deal_history import NativeDeals
    from test_retirement_venue_observations import ctrader
    from vati.funding.runtime import capture_funding
    from vati.funding.movement_journal import FinancialMovementBook
    ledger=Ledger(tmp_path/'facts.sqlite');transport=NativeDeals();transport.rows=[]
    transport.trader.update(balance=11000,moneyDigits=2,balanceVersion=2)
    detail=transport.deals[0]['closePositionDetail']
    detail.update(grossProfit=1200,swap=-100,commission=-100,balance=11000,
        moneyDigits=2,pnlConversionFee=0,balanceVersion=2)
    adapter=ctrader(transport);adapter.clock=lambda:3000
    try:
        snapshot(ledger,mark(1000))
        account=adapter.sync_account()
        result=capture_funding(ledger,adapter,account,now_ms=3000)
        assert result['deal_observation']['state']=='OBSERVED'
        assert result['financial_movements']['posted_count']==1
        snapshot(ledger,account.funding_mark)
        actual=FinancialMovementBook(ledger).projection(account.funding_mark.scope_hash)
        assert actual['current_original_source_verified'] is True
        assert Money.from_body(actual['movements'][0]['movement']['amount']).decimal==D('10')
        assert actual['movements'][0]['publication']==result['financial_movements']['last_publication']
        assert actual['risk_capital_qualified'] is actual['execution_authority'] is False
        assert not any(n in {'ProtoOANewOrderReq','ProtoOAWithdrawReq'} for n,_ in transport.requests)
    finally:ledger.close()
