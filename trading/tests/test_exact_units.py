"""Exact values preserve native precision and refuse cross-owner arithmetic."""
from dataclasses import FrozenInstanceError
from decimal import Decimal, Inexact, Rounded, localcontext

import pytest

from vati.core.units import Money, Quantity, Posting, balanced_postings, UnitError, MAX_MINOR


@pytest.mark.parametrize('number,scale',[(2**53+17,8),(-(2**63)+1,18),(0,6),(2**256-1,36)])
def test_large_native_units_roundtrip_without_float_or_context_loss(number,scale):
    money=Money(number,scale,'USD','provider:demo:asset:7')
    quantity=Quantity(number,scale,'provider:demo:instrument:42:revision:3')
    assert Money.from_body(money.body())==money and Quantity.from_body(quantity.body())==quantity
    assert money.body()['minor_units']==str(number) and quantity.body()['units']==str(number)
    with localcontext() as ambient:
        ambient.prec=2;ambient.Emax=2;ambient.Emin=-2;ambient.rounding='ROUND_UP'
        ambient.traps[Inexact]=ambient.traps[Rounded]=True
        before=ambient.copy()
        assert Money.from_decimal(money.decimal,scale=scale,currency=money.currency,asset_ref=money.asset_ref)==money
        assert Quantity.from_decimal(quantity.decimal,scale=scale,instrument_ref=quantity.instrument_ref)==quantity
        assert money.fraction==quantity.fraction
        assert ambient.flags==before.flags


def test_exact_scale_alignment_preserves_debits_fees_and_positions():
    asset='actual-owner-asset-ref';instrument='actual-owner-contract-ref'
    credit=Money(100,0,'USD',asset);fee=Money(-123,2,'USD',asset)
    assert (credit+fee).body()==Money(9877,2,'USD',asset).body()
    assert (credit-credit)==Money(0,0,'USD',asset)
    assert (Quantity(2,0,instrument)-Quantity(125,2,instrument))==Quantity(75,2,instrument)
    assert Money(-120,2,'USD',asset).rescale(1)==Money(-12,1,'USD',asset)


@pytest.mark.parametrize('value',[Decimal('1.001'),Decimal('-0.001')])
def test_unrepresentable_source_values_are_never_rounded_into_money_or_quantity(value):
    with pytest.raises(UnitError,match='NOT_REPRESENTABLE'):
        Money.from_decimal(value,scale=2,currency='USD',asset_ref='source')
    with pytest.raises(UnitError,match='NOT_REPRESENTABLE'):
        Quantity.from_decimal(value,scale=2,instrument_ref='source')


@pytest.mark.parametrize('value',[1.1,'1.1',True,Decimal('NaN'),Decimal('Infinity')])
def test_float_nonfinite_and_untyped_amounts_cannot_be_native_units(value):
    with pytest.raises(UnitError):Money.from_decimal(value,scale=2,currency='USD',asset_ref='source')
    with pytest.raises(UnitError):Quantity.from_decimal(value,scale=2,instrument_ref='source')


@pytest.mark.parametrize('change',[{'currency':'EUR'},{'asset_ref':'other-provider:asset:7'},
    {'asset_ref':'same-provider:live:asset:7'}])
def test_matching_display_names_do_not_allow_cross_currency_provider_or_realm_arithmetic(change):
    first=Money(100,2,'USD','provider:demo:asset:7')
    other=Money(**({'minor_units':100,'scale':2,'currency':first.currency,'asset_ref':first.asset_ref}|change))
    with pytest.raises(UnitError,match='CONVERSION_REQUIRED'):first+other
    with pytest.raises(UnitError,match='CONVERSION_REQUIRED'):first-other


def test_contract_revisions_and_dimensions_cannot_be_conflated():
    q=Quantity(1,0,'instrument:42:revision:1')
    with pytest.raises(UnitError,match='INSTRUMENT_MISMATCH'):q+Quantity(1,0,'instrument:42:revision:2')
    money=Money(1,0,'USD',q.instrument_ref)
    with pytest.raises(TypeError):money+q
    with pytest.raises(TypeError):q+money
    with pytest.raises(TypeError):money-q
    with pytest.raises(TypeError):q-money


@pytest.mark.parametrize('value',[True,1.0,'1',MAX_MINOR+1,-MAX_MINOR-1])
def test_minor_unit_types_and_capacity_refuse_without_truncation(value):
    with pytest.raises(UnitError):Money(value,2,'USD','source')
    with pytest.raises(UnitError):Quantity(value,2,'source')


@pytest.mark.parametrize('scale',[True,-1,4097,2.0,'2'])
def test_declared_scale_must_be_bounded_integer(scale):
    with pytest.raises(UnitError):Money(1,scale,'USD','source')
    with pytest.raises(UnitError):Quantity(1,scale,'source')


@pytest.mark.parametrize('minor',['01','+1','-0',' 1','1.0','1e2','١',True,1])
def test_serialized_minor_units_are_exact_canonical_ascii_strings(minor):
    with pytest.raises(UnitError):Money.from_body(Money(1,0,'USD','source').body()|{'minor_units':minor})
    with pytest.raises(UnitError):Quantity.from_body(Quantity(1,0,'source').body()|{'units':minor})


def test_immutable_private_views_and_failed_rescale_preserve_original_value():
    m=Money(123,2,'USD','source');q=Quantity(123,2,'source')
    m.body()['minor_units']='999';q.body()['units']='999'
    assert m.minor_units==q.units==123
    with pytest.raises(FrozenInstanceError):m.minor_units=999
    with pytest.raises(FrozenInstanceError):q.units=999
    with pytest.raises(UnitError,match='WOULD_ROUND'):m.rescale(1)
    with pytest.raises(UnitError,match='WOULD_ROUND'):q.rescale(1)
    with pytest.raises(UnitError):Money(MAX_MINOR,0,'USD','source')+Money(1,0,'USD','source')
    with pytest.raises(UnitError):Quantity(MAX_MINOR,0,'source')+Quantity(1,0,'source')


def test_postings_balance_exactly_per_asset_with_declared_scales():
    first=Posting('broker-cash',Money(123,2,'USD','asset:USD'))
    rows=[first,Posting('capital-clearing',Money(-1230,3,'USD','asset:USD')),
        Posting('broker-eur',Money(10,0,'EUR','asset:EUR')),
        Posting('eur-clearing',Money(-1000,2,'EUR','asset:EUR'))]
    assert balanced_postings(rows)==tuple(rows)
    assert Posting.from_body(first.body())==first


@pytest.mark.parametrize('counter',[
    Money(-122,2,'USD','asset:USD'),Money(-123,2,'EUR','asset:USD'),
    Money(-123,2,'USD','other-provider:USD')])
def test_offsetting_labels_cannot_conceal_an_unbalanced_or_foreign_asset(counter):
    with pytest.raises(UnitError,match='UNBALANCED'):
        balanced_postings([Posting('cash',Money(123,2,'USD','asset:USD')),Posting('offset',counter)])


def test_a_posting_to_its_own_account_is_not_a_counterparty_or_settlement():
    with pytest.raises(UnitError,match='COUNTERACCOUNT_MISSING'):
        balanced_postings([Posting('same',Money(1,0,'USD','asset')),Posting('same',Money(-1,0,'USD','asset'))])
    with pytest.raises(UnitError):Posting('cash',Quantity(1,0,'asset'))
    with pytest.raises(UnitError):balanced_postings([])
