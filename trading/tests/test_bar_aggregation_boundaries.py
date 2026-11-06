"""Actual inherited aggregator ordering, failure atomicity and numeric boundaries."""
from decimal import Decimal,DefaultContext,Inexact,Overflow,ROUND_DOWN,localcontext

import pytest

from vati.market_data.bars import BarAggregator,Tick


def ticks():
    return [Tick(1,Decimal('1.123456'),Decimal('1.123458'),Decimal('0.123456')),
            Tick(2,Decimal('1.234567'),Decimal('1.234569'),Decimal('0.234567'))]


@pytest.mark.parametrize('setting',['precision','rounding','exponents','traps','mutable-default'])
def test_original_tick_aggregation_is_independent_of_caller_context(setting):
    expected=list(BarAggregator('EURUSD',60000).run(ticks()))
    default=DefaultContext.copy()
    try:
        with localcontext() as context:
            if setting=='precision':context.prec=3
            elif setting=='rounding':context.prec=6;context.rounding=ROUND_DOWN
            elif setting=='exponents':context.Emax=0;context.Emin=0
            elif setting=='traps':context.prec=3;context.traps[Inexact]=True
            else:DefaultContext.prec=3;DefaultContext.rounding=ROUND_DOWN;DefaultContext.Emax=0
            before=context.copy()
            actual=list(BarAggregator('EURUSD',60000).run(ticks()))
            assert actual==expected
            assert context.flags==before.flags and context.traps==before.traps
            assert (context.prec,context.rounding,context.Emax,context.Emin)==(before.prec,before.rounding,before.Emax,before.Emin)
    finally:
        for field in ('prec','rounding','Emin','Emax','capitals','clamp'):setattr(DefaultContext,field,getattr(default,field))
        DefaultContext.traps=default.traps.copy();DefaultContext.flags=default.flags.copy()


@pytest.mark.parametrize('late',[1,60000])
def test_out_of_order_tick_refuses_before_publishing_or_changing_a_bar(late):
    agg=BarAggregator('EURUSD',60000);agg.push(Tick(60001,Decimal('1'),Decimal('2')))
    with pytest.raises(ValueError,match='order'):agg.push(Tick(late,Decimal('3'),Decimal('4')))
    original=agg.finish();assert original.start_ms==60000 and original.ticks==1 and original.open==Decimal('1.5')
    assert agg.finish() is None
    # Finish flushes output; it cannot reopen an older source interval.
    with pytest.raises(ValueError,match='order'):agg.push(Tick(late,Decimal('3'),Decimal('4')))


@pytest.mark.parametrize('bad',[True,1.5,0,-1])
def test_interval_requires_a_positive_integer(bad):
    with pytest.raises(ValueError):BarAggregator('EURUSD',bad)


@pytest.mark.parametrize('field,value',[
    ('ts_ms',True),('ts_ms',1.5),('bid',1.0),('ask',Decimal('NaN')),
    ('bid',Decimal('Infinity')),('volume',Decimal('-1')),('volume',Decimal('sNaN')),
    ('bid',Decimal('4')),
])
def test_invalid_new_interval_cannot_flush_the_current_original(field,value):
    agg=BarAggregator('EURUSD',60000);agg.push(Tick(1,Decimal('1'),Decimal('2')))
    row={'ts_ms':60001,'bid':Decimal('2'),'ask':Decimal('3'),'volume':Decimal('0')};row[field]=value
    with pytest.raises(ValueError):agg.push(Tick(**row))
    bar=agg.finish();assert bar is not None
    assert bar.start_ms==0 and bar.ticks==1 and bar.close==Decimal('1.5')


def test_equal_clock_order_is_preserved_without_inventing_sequence_or_gap_bars():
    rows=[Tick(1,Decimal('1'),Decimal('3'),Decimal('2')),
          Tick(1,Decimal('3'),Decimal('5'),Decimal('4')),
          Tick(180001,Decimal('5'),Decimal('7'),Decimal('6'))]
    actual=list(BarAggregator('EURUSD',60000).run(rows))
    assert [b.start_ms for b in actual]==[0,180000]
    assert (actual[0].open,actual[0].close,actual[0].ticks,actual[0].volume)==(Decimal('2'),Decimal('4'),2,Decimal('6'))
    assert actual[1].ticks==1 and actual[1].open==Decimal('6')


def test_negative_instrument_prices_remain_valid_and_mid_and_range_are_context_stable():
    tick=Tick(1,Decimal('-40.123456'),Decimal('-40.123454'))
    bar=list(BarAggregator('WTI',60000).run([tick,Tick(2,Decimal('-39.123456'),Decimal('-39.123454'))]))[0]
    with localcontext() as context:
        context.prec=3;context.traps[Inexact]=True
        assert tick.mid==Decimal('-40.123455') and bar.range==Decimal('1')


@pytest.mark.parametrize('same_interval',[False,True])
@pytest.mark.parametrize('field',['price','volume'])
def test_failed_arithmetic_neither_flushes_nor_partially_updates_original_state(same_interval,field):
    agg=BarAggregator('EURUSD',60000);agg.push(Tick(1,Decimal('1'),Decimal('2'),Decimal('3')))
    bid,ask,volume=(Decimal('1e999999999'),Decimal('1e999999999'),Decimal('0')) if field=='price' else (Decimal('3'),Decimal('4'),Decimal('1e999999999'))
    with pytest.raises(Overflow):
        agg.push(Tick(2 if same_interval else 60001,bid,ask,volume))
    bar=agg.finish()
    assert (bar.start_ms,bar.ticks,bar.volume,bar.open,bar.close)==(0,1,Decimal('3'),Decimal('1.5'),Decimal('1.5'))


def test_empty_finish_and_negative_epoch_alignment_preserve_existing_utc_semantics():
    agg=BarAggregator('HISTORICAL',60000);assert agg.finish() is None
    bars=list(agg.run([Tick(-1,Decimal('0'),Decimal('0'))]))
    assert len(bars)==1 and bars[0].start_ms==-60000 and bars[0].end_ms==0 and bars[0].open==Decimal('0')


@pytest.mark.parametrize('timestamp',[60001,60002,119999])
def test_resuming_after_finish_cannot_reopen_an_already_emitted_interval(timestamp):
    agg=BarAggregator('EURUSD',60000);agg.push(Tick(60001,Decimal('1'),Decimal('2')))
    original=agg.finish();assert original.start_ms==60000
    with pytest.raises(ValueError,match='order'):
        agg.push(Tick(timestamp,Decimal('3'),Decimal('4')))
    assert agg.finish() is None
    assert agg.push(Tick(120000,Decimal('5'),Decimal('6'))) is None
    following=agg.finish();assert following.start_ms==120000 and following.ticks==1
