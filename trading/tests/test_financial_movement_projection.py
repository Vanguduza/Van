"""Real native source ledger facts -> exact balanced projection, never permission."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace, FrozenInstanceError
from decimal import Decimal

import pytest

from test_funding_journal import statement
from vati.core import Ledger, EventKind
from vati.core.canonical import canonical_hash
from vati.core.units import Money, UnitError, balanced_postings
from vati.funding.journal import FundingBook
from vati.funding.postings import FinancialMovement


def original(tmp_path,operation='BALANCE_DEPOSIT',delta='0.01234567',**changes):
    source=statement();source=replace(source,**changes,movements=(replace(source.movements[0],
        operation=operation,delta=Decimal(delta),native_id=2**53+99),))
    with closing(Ledger(tmp_path/'source.sqlite')) as ledger:
        receipt=FundingBook(ledger,clock=lambda:5000).record_statement(source)
        event=next(e for e in ledger.iter(EventKind.FUNDING_STATEMENT) if e.hash==receipt['statement_ref'])
    return source,event


@pytest.mark.parametrize('operation,delta,state,category',[
    ('BALANCE_DEPOSIT','0.01234567','OBSERVED_CASH_NOT_SETTLEMENT','EXTERNAL_CAPITAL'),
    ('BALANCE_WITHDRAW','-0.01234567','OBSERVED_CASH_NOT_SETTLEMENT','EXTERNAL_CAPITAL'),
    ('BALANCE_DEPOSIT_NONWITHDRAWABLE_BONUS','1','RESTRICTED_CREDIT_MEMORANDUM','RESTRICTED_CREDIT'),
    ('NATIVE_UNKNOWN','1','UNRESOLVED_NATIVE_MOVEMENT','UNRESOLVED'),
    ('BALANCE_DEPOSIT','-1','UNRESOLVED_NATIVE_MOVEMENT','UNRESOLVED'),
    ('BALANCE_DEPOSIT_IB_COMMISSIONS','1','OBSERVED_CASH_NOT_SETTLEMENT','OTHER_BUSINESS_INCOME_OR_EXPENSE'),
    ('BALANCE_WITHDRAW_ROLLOVER','-1','OBSERVED_CASH_NOT_SETTLEMENT','ACCOUNT_INCOME_OR_EXPENSE'),
    ('BALANCE_DEPOSIT_CONVERTED_BONUS','1','OBSERVED_CASH_NOT_SETTLEMENT','BROKER_SUPPORT_CAPITAL'),
    ('BALANCE_DEPOSIT','0','OBSERVED_CASH_NOT_SETTLEMENT','EXTERNAL_CAPITAL'),
])
def test_native_economic_classes_keep_exact_original_sources_and_balanced_legs(tmp_path,operation,delta,state,category):
    source,event=original(tmp_path,operation,delta)
    movement=FinancialMovement(event,source.movements[0].native_id,recorded_at_ms=6000);body=movement.body()
    assert body['state']==state and body['classification']['category']==category
    assert body['native_id']==str(2**53+99) and body['source_statement_ref']==event.hash
    assert body['source_row_digest']==canonical_hash(source.movements[0].body())
    assert body['source_available_at_ms']==5000 and body['recorded_at_ms']==6000
    amount=Money.from_body(body['amount']);assert amount.decimal==Decimal(delta) and amount.scale==8
    assert balanced_postings(movement.postings)==movement.postings
    assert sum(p.amount.fraction for p in movement.postings)==0
    assert body['risk_capital_qualified'] is body['trade_alpha_claimed'] is body['execution_authority'] is False
    assert body['settlement_qualification']=='NOT_ISSUED'
    if state!='OBSERVED_CASH_NOT_SETTLEMENT':
        assert all('observed-broker-cash' not in p.account_ref for p in movement.postings)


def test_native_realm_and_asset_identity_cannot_be_erased_by_currency_label(tmp_path):
    source,a=original(tmp_path)
    _,b=original(tmp_path,environment='LIVE')
    first=FinancialMovement(a,source.movements[0].native_id,recorded_at_ms=6000)
    second=FinancialMovement(b,source.movements[0].native_id,recorded_at_ms=6000)
    assert first.body()['amount']['currency']==second.body()['amount']['currency']
    assert first.body()['amount']['asset_ref']!=second.body()['amount']['asset_ref']
    with pytest.raises(UnitError):balanced_postings([first.postings[0],second.postings[1]])


@pytest.mark.parametrize('damage',['producer','kind','seal','scope','key','self-grant','conflict','clock'])
def test_even_sealed_incompatible_native_envelopes_cannot_be_projected(tmp_path,damage):
    source,event=original(tmp_path);payload=deepcopy(event.payload);updates={}
    if damage=='producer':updates['producer']='another-owner'
    elif damage=='kind':updates['kind']=EventKind.SESSION
    elif damage=='scope':payload['scope_hash']='f'*64
    elif damage=='key':payload['content_key']='f'*64
    elif damage=='self-grant':payload['execution_authority']=True
    elif damage=='conflict':payload['state']='CONFLICT'
    elif damage=='clock':updates['event_time_ms']=event.event_time_ms+1
    changed=replace(event,payload=payload,**updates)
    changed=replace(changed,hash='f'*64 if damage=='seal' else canonical_hash(changed.body()))
    with pytest.raises(ValueError):FinancialMovement(changed,source.movements[0].native_id,recorded_at_ms=6000)


def test_missing_native_row_early_availability_and_mutation_never_invent_postings(tmp_path):
    source,event=original(tmp_path);identifier=source.movements[0].native_id
    with pytest.raises(ValueError):FinancialMovement(event,identifier+1,recorded_at_ms=6000)
    with pytest.raises(ValueError):FinancialMovement(event,identifier,recorded_at_ms=4999)
    movement=FinancialMovement(event,identifier,recorded_at_ms=6000);before=movement.body()
    movement.body()['amount']['minor_units']='999'
    assert movement.body()==before
    with pytest.raises(FrozenInstanceError):movement._body_json=b'{}'
