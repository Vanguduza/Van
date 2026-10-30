"""Funding draft values and exact bindings; no provider or payment admission."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal,Inexact,localcontext

import pytest

from vati.core.units import Money
from vati.funding.payment_contracts import BeneficiaryRef,PaymentFee,PaymentQuote,PaymentIntent,PaymentContractError


def usd(units):return Money(units,2,'USD','provider:usd')


def quote():
    beneficiary=BeneficiaryRef('FIXTURE_PROVIDER','DEMO','owner:one','a'*64,'b'*64,'c'*64)
    return PaymentQuote('d'*64,1,beneficiary,usd(10000),usd(10100),
        (PaymentFee('service',usd(100),True),),'Invoice #123 / 零',1000,2000)


def intent():return PaymentIntent('request:original','WITHDRAW',quote())


def binding(value,**changes):
    values={'expected_intent_hash':value.intent_hash,'owner_ref':'owner:one','account_scope_ref':'a'*64,
        'beneficiary_digest':'b'*64,'now_ms':1500};values.update(changes);return values


def test_full_draft_cold_roundtrip_preserves_exact_money_and_remains_unapproved():
    original=intent();body=original.body();copy=PaymentIntent.from_body(deepcopy(body))
    assert copy==original and copy.intent_hash==original.intent_hash
    assert body['state']=='DRAFT_NOT_APPROVED' and body['execution_authority'] is body['provider_qualified'] is False
    assert body['quote']['beneficiary']['verification_state']=='UNVERIFIED_REFERENCE'
    assert body['quote']['amount']['minor_units']=='10000'
    assert copy.validate_binding(**binding(original)) is None
    assert original.body()==body


@pytest.mark.parametrize('change',['fee','revision','reference','quote-source','beneficiary','proof','owner','account','expiry','operation','request'])
def test_changed_valid_input_cannot_use_the_original_exact_binding(change):
    original=intent();q=original.quote
    if change=='fee':q=replace(q,fees=(PaymentFee('service',usd(200),True),),quoted_debit=usd(10200))
    elif change=='revision':q=replace(q,revision=2)
    elif change=='reference':q=replace(q,reference='Invoice #124')
    elif change=='quote-source':q=replace(q,quote_record_ref='e'*64)
    elif change=='expiry':q=replace(q,expires_at_ms=2001)
    else:
        field={'beneficiary':'beneficiary_digest','proof':'verification_record_ref','owner':'owner_ref','account':'account_scope_ref'}.get(change)
        if field:q=replace(q,beneficiary=replace(q.beneficiary,**{field:'owner:two' if field=='owner_ref' else 'e'*64}))
    changed=replace(original,quote=q,**({'operation':'TRANSFER'} if change=='operation' else {'request_id':'request:new'} if change=='request' else {}))
    assert changed.intent_hash!=original.intent_hash
    with pytest.raises(PaymentContractError,match='INTENT_BINDING_DIFFERS'):
        changed.validate_binding(**binding(original))


@pytest.mark.parametrize('field,value',[
    ('owner_ref','owner:two'),('account_scope_ref','e'*64),('beneficiary_digest','e'*64),
    ('now_ms',999),('now_ms',2000),('now_ms',2001),('now_ms',True),('now_ms',1500.0),
])
def test_foreign_or_stale_context_refuses_without_mutating_the_draft(field,value):
    original=intent();body=original.body()
    with pytest.raises(PaymentContractError):original.validate_binding(**binding(original,**{field:value}))
    assert original.body()==body


@pytest.mark.parametrize('now',[1000,1999])
def test_exact_quote_time_boundaries_are_half_open(now):
    original=intent();original.validate_binding(**binding(original,now_ms=now))


def test_fee_identity_order_is_canonical_and_external_asset_charges_are_not_double_counted():
    gas=Money(7,8,'ETH','network:ethereum:eth')
    q=replace(quote(),fees=(PaymentFee('gas',gas,False),PaymentFee('service',usd(100),True),PaymentFee('additional',usd(50),False)))
    assert {(m.currency,m.asset_ref):(m.minor_units,m.scale) for m in q.declared_debits()}=={
        ('USD','provider:usd'):(10150,2),('ETH','network:ethereum:eth'):(7,8)}
    assert replace(q,fees=tuple(reversed(q.fees))).quote_hash==q.quote_hash
    assert PaymentQuote.from_body(q.body())==replace(q,fees=tuple(sorted(q.fees,key=lambda f:f.fee_id)))


def test_cross_asset_provider_claim_needs_original_conversion_reference_and_never_infers_a_rate():
    eur=Money(9200,2,'EUR','provider:eur')
    with pytest.raises(PaymentContractError,match='CONVERSION_REFERENCE_REQUIRED'):
        replace(quote(),quoted_debit=eur,fees=())
    q=replace(quote(),quoted_debit=eur,fees=(),conversion_record_ref='f'*64)
    assert q.declared_debits()==(eur,) and q.amount==usd(10000)
    assert q.body()['provider_qualified'] is q.body()['execution_authority'] is False
    assert PaymentQuote.from_body(q.body())==q


@pytest.mark.parametrize('bad',['total','included-foreign','duplicate-fee','negative-fee','zero-amount','bool-revision','float-expiry','fee-list','ambiguous-inclusion'])
def test_invalid_quote_economics_or_types_refuse(bad):
    q=quote()
    with pytest.raises((PaymentContractError,ValueError)):
        if bad=='total':replace(q,quoted_debit=usd(10099))
        elif bad=='included-foreign':replace(q,fees=(PaymentFee('gas',Money(1,8,'ETH','network:eth'),True),))
        elif bad=='duplicate-fee':replace(q,fees=q.fees+q.fees)
        elif bad=='negative-fee':PaymentFee('fee',usd(-1),False)
        elif bad=='zero-amount':replace(q,amount=usd(0))
        elif bad=='bool-revision':replace(q,revision=True)
        elif bad=='float-expiry':replace(q,expires_at_ms=2000.0)
        elif bad=='fee-list':replace(q,fees=list(q.fees))
        else:PaymentFee('fee',usd(1),0)


@pytest.mark.parametrize('change',['approved','authority','qualified','numeric-false','numeric-revision','numeric-scale','minor-float','quote-hash','extra-secret','beneficiary-verified'])
def test_wire_resealing_cannot_upgrade_a_draft_or_hide_unknown_fields(change):
    body=intent().body()
    if change=='approved':body['state']='APPROVED'
    elif change=='authority':body['execution_authority']=True
    elif change=='qualified':body['quote']['provider_qualified']=True
    elif change=='numeric-false':body['execution_authority']=0
    elif change=='numeric-revision':body['quote']['revision']=1.0
    elif change=='numeric-scale':body['quote']['amount']['scale']=2.0
    elif change=='minor-float':body['quote']['amount']['minor_units']=10000.0
    elif change=='quote-hash':body['quote_hash']='e'*64
    elif change=='extra-secret':body['payment_token']='fixture-value-not-an-instrument'
    else:body['quote']['beneficiary']['verification_state']='VERIFIED'
    with pytest.raises(PaymentContractError,match='WIRE_FORMAT_INVALID'):PaymentIntent.from_body(body)


def test_exact_requirements_and_hashes_ignore_ambient_decimal_settings():
    original=intent();expected=original.body();digest=original.intent_hash
    with localcontext() as context:
        context.prec=2;context.Emax=0;context.Emin=0;context.traps[Inexact]=True
        assert PaymentIntent.from_body(expected).intent_hash==digest
        assert original.quote.declared_debits()==(usd(10100),)
        assert original.quote.amount.decimal==Decimal('100.00')


def test_value_and_binding_operations_cannot_open_files_or_provider_connections(monkeypatch):
    import builtins,socket
    def forbidden(*args,**kwargs):pytest.fail('a pure draft tried to perform I/O')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(socket,'socket',forbidden)
    original=intent();copy=PaymentIntent.from_body(original.body());copy.validate_binding(**binding(original))
    assert copy.body()['state']=='DRAFT_NOT_APPROVED'
