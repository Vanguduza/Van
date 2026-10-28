"""Independent rational cost oracles under caller-controlled Decimal contexts."""
from dataclasses import replace
from contextlib import closing
from decimal import Decimal as D, localcontext, Inexact, Rounded, ROUND_UP, ROUND_DOWN
from fractions import Fraction as F

import pytest

from vati.execution.base import ExecutionReceipt
from vati.execution.tca import compute_tca
from vati.risk.contracts import Direction


def original(**changes):
    return replace(ExecutionReceipt('exact-cost', 'd'*64, 'paper', 'PARTIAL',
        D('0.123456789123456789'), D('100.000000000000000029'),
        D('100.000000000000000001'), D('100.000000000000000017'),
        D('100.000000000000000019'), True, 1000, 1001,
        spread_at_submit=D('0.000000000000000003'), fees=D('-0.0000000000000000000000003')),
        **changes).sealed()


@pytest.mark.parametrize('direction', list(Direction))
@pytest.mark.parametrize('precision,rounding,traps', [(2, ROUND_UP, False), (7, ROUND_DOWN, False),
    (3, ROUND_UP, True), (80, ROUND_DOWN, True)])
def test_economic_values_are_exact_and_independent_of_callers_context(direction, precision, rounding, traps):
    r = original(); value = D('123456789.000000000123456789'); model = D('0.000031')
    baseline = compute_tca(r, direction=direction, qty=r.filled_qty, value_per_unit=value, modelled_cost_pct=model)
    sign = 1 if direction is Direction.LONG else -1
    oracle = (F(r.average_fill)-F(r.decision_price))*sign*F(r.filled_qty)*F(value)+F(r.fees)
    notional = F(r.decision_price)*F(r.filled_qty)*F(value)
    with localcontext() as context:
        context.prec=precision;context.rounding=rounding;context.Emax=9;context.Emin=-9
        context.traps[Inexact]=traps;context.traps[Rounded]=traps
        before=context.copy()
        result=compute_tca(r,direction=direction,qty=r.filled_qty,value_per_unit=value,modelled_cost_pct=model)
        assert result.as_dict()==baseline.as_dict()
        assert context.prec==before.prec and context.rounding==before.rounding
        assert context.traps==before.traps and context.flags==before.flags
    assert F(result.implementation_shortfall)==oracle
    assert F(result.reference_notional)==notional
    components=F(result.delay_cost)+F(result.submission_cost)+F(result.slippage)
    assert components*F(r.filled_qty)*F(value)+F(result.fees)==oracle
    assert F(result.spread_cost)==F(r.spread_at_submit)*F(r.filled_qty)*F(value)/2


def test_large_offset_does_not_erase_one_atom_adverse_move():
    r=original(decision_price=D('1'+'0'*120),arrival_price=D('1'+'0'*120),
        submitted_price=D('1'+'0'*120),average_fill=D('1'+'0'*119+'1'),
        filled_qty=D('0.00000001'),fees=D('-0.000000001'))
    result=compute_tca(r,direction=Direction.LONG,qty=r.filled_qty,value_per_unit=D('100000000'),modelled_cost_pct=D('0'))
    assert F(result.implementation_shortfall)==F(999999999,1000000000)
    assert result.cost_ratio==D('Infinity')


@pytest.mark.parametrize('field,value', [('filled_qty', D('1e-4097')),
    ('fees',D('1e4097')),('decision_price',D('9'*4097))])
def test_unbounded_decimal_inputs_are_refused_before_cost_materialization(field,value):
    r=original(**{field:value})
    with pytest.raises(ValueError,match='capacity'):
        compute_tca(r,direction=Direction.LONG,qty=r.filled_qty,value_per_unit=D('1'),modelled_cost_pct=D('0.01'))


@pytest.mark.parametrize('model', ['0','0.000031'])
def test_exact_basis_survives_wire_roundtrip_and_hostile_validation(model):
    import json
    from vati.execution.tca import validate_tca_arithmetic
    r=original()
    body=compute_tca(r,direction=Direction.SHORT,qty=r.filled_qty,value_per_unit=D('100000'),modelled_cost_pct=D(model)).as_dict()
    with localcontext() as context:
        context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
        validate_tca_arithmetic(json.loads(json.dumps(body)))
    basis=body['arithmetic']
    as_fraction=lambda p:F(int(p['numerator']),int(p['denominator']))
    assert sum(map(as_fraction,basis['components'].values()),F(0))==as_fraction(basis['direct_cost'])
    assert basis['fee_completeness']=='RECEIPT_INPUT_ONLY_NOT_PROVIDER_COMPLETENESS'
    assert basis['execution_authority'] is False and basis['settlement_qualified'] is False
    assert (basis['cost_ratio_fraction'] is None)==(model=='0')


@pytest.mark.parametrize('field', ['cost_ratio','implementation_shortfall','slippage','delay_cost',
    'submission_cost','reference_notional','realised_cost_pct','fees','filled_quantity',
    'contract_value_per_price_unit','measurement_version'])
def test_resealed_durable_cost_corruption_cannot_enter_broker_learning(field):
    from vati.core import EventKind,Ledger,make_event
    from vati.learning import Environment
    from vati.learning.hooks import LearningHooks
    from vati.learning.replay import restore_learning_runtime
    r=original();body=compute_tca(r,direction=Direction.LONG,qty=r.filled_qty,value_per_unit=D('100000'),modelled_cost_pct=D('0.01')).as_dict()
    body|={'learning_environment':'DEMO','broker':'paper','symbol':'EURUSD','session':'LONDON',
           'event_window':'NONE','rejected':False}
    body[field]='900' if field!='measurement_version' else 'invented'
    with closing(Ledger()) as ledger:
        event=make_event(EventKind.TCA_RECORD,'vati-account-lifecycle',body,
            event_time_ms=1001,received_time_ms=1001,correlation_id=r.trade_intent_id)
        ledger.append(event)
        hooks=LearningHooks(Environment.DEMO)
        hooks.on_tca(ledger,trade_intent_id=r.trade_intent_id,symbol='EURUSD',session='LONDON',event_window='NONE',
            cost_ratio=D(body['cost_ratio']),slippage=D(body['slippage']))
        assert not hooks.brokers.profiles and hooks.refusals
        cold=LearningHooks(Environment.DEMO)
        report=restore_learning_runtime(ledger,cold,{})
        assert not cold.brokers.profiles


def test_existing_legacy_tca_without_new_arithmetic_remains_usable():
    from vati.execution.tca import validate_tca_arithmetic
    validate_tca_arithmetic({'measurement_version':'tca/2.0.0','cost_ratio':'1.25'})


def test_legacy_numeric_spelling_does_not_rewrite_or_conflict_with_original_measurement():
    from vati.execution.tca import same_tca_measurement
    r=original();current=compute_tca(r,direction=Direction.LONG,qty=r.filled_qty,
        value_per_unit=D('100000'),modelled_cost_pct=D('0.01')).as_dict()
    legacy={k:v for k,v in current.items() if k!='arithmetic'}
    legacy['reference_notional']=legacy['reference_notional']+'0' if '.' in legacy['reference_notional'] else legacy['reference_notional']+'.0'
    assert same_tca_measurement(legacy,current)
    assert 'arithmetic' not in legacy
    assert not same_tca_measurement(legacy|{'implementation_shortfall':'999'},current)


@pytest.mark.parametrize('kind',['TCA_RECORD','TRADE_EXPERIENCE_ARTIFACT'])
def test_exact_cost_claim_cannot_be_laundered_through_an_artifact(kind):
    from vati.core import EventKind,make_event
    from vati.learning.evidence import EvidenceRecord,EvidenceClass,EvidenceError
    from vati.learning import Environment
    r=original();body=compute_tca(r,direction=Direction.LONG,qty=r.filled_qty,value_per_unit=D('100000'),modelled_cost_pct=D('0.01')).as_dict()
    body['implementation_shortfall']='999'
    if kind=='TRADE_EXPERIENCE_ARTIFACT':
        body={'execution':{'tca':body},'environment':'DEMO'}
    else:body['learning_environment']='DEMO'
    event=make_event(EventKind(kind),'vati-account-lifecycle',body,event_time_ms=1001,received_time_ms=1001,correlation_id=r.trade_intent_id)
    with pytest.raises(EvidenceError,match='exact arithmetic'):
        evidence_class=EvidenceClass.VTIL_ARTIFACT if kind=='TRADE_EXPERIENCE_ARTIFACT' else EvidenceClass.TCA_RECORD
        EvidenceRecord.from_content(evidence_class,event.body(),session_environment=Environment.DEMO)
