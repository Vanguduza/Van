"""Original source math; projected resources are not admitted obligations."""
from decimal import Decimal as D
from test_current_entry_risk_source import current_entry
from vati.core import EventKind
from vati.core.units import Money
from vati.risk import TradingMandate
from vati.risk.mandate_source import capture_mandate_source
from vati.risk.entry_resource_projection import project_entry_resources


def projection(ledger,command,margin_ref,current_ref,clock):
    original=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.payload['decision']['decision_hash']==command.decision_hash)
    raw=original.payload['inputs']['mandate'];m=TradingMandate.from_mapping(raw)
    proof=capture_mandate_source(m,raw,now_ms=clock['ms'])
    assert proof['state']=='ORIGINAL_BOUND'
    return project_entry_resources(ledger,command,margin_ref,current_ref,proof,at_ms=clock['ms']).body()


def test_actual_quote_and_signed_policy_produce_exact_resource_burdens_without_a_grant(tmp_path,eurusd):
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd)
    try:
        before=ledger.count();p=projection(ledger,command,margin_ref,current_ref,clock)
        amounts={k:Money.from_body(v).decimal for k,v in p['burdens'].items()}
        assert amounts=={'free_cash':D('33.00'),'margin_floor_equity':D('66.00'),'stop_risk':D('22.00'),
            'currency_leg_up:EUR':D('22.00'),'currency_leg_down:EUR':D('0'),
            'currency_leg_up:USD':D('0'),'currency_leg_down:USD':D('22.00')}
        assert p['fee_state']=='UNMEASURED_NOT_ZERO' and p['obligations_complete'] is False
        assert p['reservation_qualified'] is p['execution_authority'] is False
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_margin_rounds_to_native_money_before_applying_the_existing_floor(tmp_path,eurusd):
    sdk,clock,ledger,command,margin_ref,current_ref=current_entry(tmp_path,eurusd,native_margin=D('199.995'))
    try:
        p=projection(ledger,command,margin_ref,current_ref,clock)
        assert Money.from_body(p['burdens']['free_cash']).decimal==D('200.00')
        assert Money.from_body(p['burdens']['margin_floor_equity']).decimal==D('400.00')
        assert not sdk.sent
    finally:ledger.close()
