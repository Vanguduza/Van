"""Immutable sampled flow-adjusted calculation, never a risk-admission grant.

All inputs must already be normalized, scoped and source-verified by their
owner. This arithmetic model cannot establish provider history, clocks or
collateral. Native readers must preserve missing flow valuations as unknown.
"""
from dataclasses import dataclass
from decimal import Decimal
import json
import re

from vati.core.canonical import canonical_json
from vati.core.units import UnitError
from vati.funding.native import native_int
from vati.funding.unitization import FlowKind, FlowPoint, NetEquityPoint, unitize, _number

MAX_POINTS=4096
DIGEST=re.compile(r'[0-9a-f]{64}',re.ASCII)


def _reference(value):
    if not isinstance(value,str) or DIGEST.fullmatch(value) is None:
        raise UnitError('FLOW_RISK_EXACT_SOURCE_REFERENCE_REQUIRED')
    return value


@dataclass(frozen=True,init=False)
class FlowAdjustedRisk:
    _body_json: bytes

    def __init__(self,baseline,closing,flows=(),*,samples=()):
        if type(baseline) is not NetEquityPoint or type(closing) is not NetEquityPoint:
            raise UnitError('FLOW_RISK_TYPED_VALUATIONS_REQUIRED')
        if (not isinstance(flows,(list,tuple)) or not isinstance(samples,(list,tuple))
                or len(flows)+len(samples)>MAX_POINTS):
            raise UnitError('FLOW_RISK_POINT_CAPACITY')
        if any(type(p) is not FlowPoint for p in flows) or any(type(p) is not NetEquityPoint for p in samples):
            raise UnitError('FLOW_RISK_TYPED_SOURCE_POINTS_REQUIRED')
        points=[baseline,*flows,*samples,closing]
        refs=[]
        for point in points:
            _reference(point.scope_hash);refs.append(_reference(point.source_ref))
            if point.scope_hash!=baseline.scope_hash:raise UnitError('FLOW_RISK_NATIVE_SCOPE_MISMATCH')
            try:
                native_int(point.at_ms,minimum=0)
                if point.native_order is not None:native_int(point.native_order,minimum=0)
            except ValueError as error:raise UnitError('FLOW_RISK_NATIVE_CLOCK_OR_ORDER_INVALID') from error
        if len(set(refs))!=len(refs):raise UnitError('FLOW_RISK_SOURCE_IDENTITY_REUSED')
        # Zero-flow observations expose intermediate peaks/troughs without
        # issuing or redeeming units. Equal-time ambiguity retains the existing
        # calculator's native-order refusal; source IDs never supply ordering.
        try:
            states={(p.at_ms,p.native_order,_number(p.equity)) for p in (baseline,closing)}
            observations=[];redundant=[]
            for point in samples:
                state=(point.at_ms,point.native_order,_number(point.equity))
                if state in states:
                    redundant.append(point.source_ref)
                    continue
                states.add(state)
                observations.append(FlowPoint(point.scope_hash,point.at_ms,Decimal(0),point.equity,
                    FlowKind.INTERNAL,point.source_ref,point.native_order))
            result=unitize(baseline,closing,[*flows,*observations])
        except (ValueError,TypeError,ArithmeticError) as error:
            raise UnitError('FLOW_RISK_NORMALIZED_INPUT_INVALID') from error
        body={'schema':'vati.flow-adjusted-risk/1','policy_version':'sampled-flow-risk/1.0.0',
            'scope_hash':baseline.scope_hash,'state':result['status'],'reason':result['reason'],
            'calculation':result,'source_refs':refs,'flow_count':len(flows),'sample_count':len(samples),
            'redundant_sample_refs':redundant,
            'drawdown_basis':'SAMPLED_NORMALIZED_VALUES_NOT_INTRAPERIOD_EXTREMA',
            'input_qualification':'NORMALIZED_INPUTS_REQUIRED_NOT_CERTIFIED_BY_CALCULATOR',
            'native_source_qualification':'NOT_ISSUED','risk_capital_qualified':False,
            'settlement_qualification':'NOT_ISSUED','execution_authority':False}
        object.__setattr__(self,'_body_json',canonical_json(body).encode())

    def body(self):
        return json.loads(self._body_json)
