"""Native producers must not erase ambiguous data before the kernel sees it."""
from dataclasses import replace

import pytest

from conftest import mandate_dict
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_bridge import BridgeRequest,Mt5BridgeAdapter,Mt5BridgeClient
from vati.risk.mandate import MandateError,PlatformCeilings,TradingMandate


@pytest.mark.parametrize('field',['verified','hedging'])
def test_actual_bridge_decoder_cannot_turn_a_false_string_into_a_verified_fact(field):
    account={'equity':'10000','balance':'10000','currency':'USD','verified':True,'hedging':True,field:'false'}
    def transport(request):
        assert client.verify(BridgeRequest(**request))
        return {'nonce':request['nonce'],'worker_time_ms':request['issued_ms'],'account':account}
    client=Mt5BridgeClient(signing_key=b'fixture-bridge-request-key',transport=transport)
    adapter=Mt5BridgeAdapter(client,clock=lambda:1000)
    with pytest.raises((ValueError,VenueUnavailable)):
        adapter.sync_account()


@pytest.mark.parametrize('field',['weekend','drawdown'])
def test_owner_policy_loader_does_not_coerce_false_text_to_a_true_permission(field):
    raw=mandate_dict()
    if field=='weekend':raw['weekend_hold_allowed']='false'
    else:raw['drawdown_tiers']=[{'threshold':'0.05','multiplier':'0.5','top_tier_only':'false'},
        {'threshold':'0.10','multiplier':'0','top_tier_only':False}]
    with pytest.raises(MandateError):TradingMandate.from_mapping(raw)


def test_explicit_false_policy_remains_false_and_direct_objects_do_not_bypass_validation():
    raw=mandate_dict(weekend_hold_allowed=False)
    raw['drawdown_tiers']=[{'threshold':'0.05','multiplier':'0.5','top_tier_only':False},
        {'threshold':'0.10','multiplier':'0','top_tier_only':False}]
    admitted=TradingMandate.from_mapping(raw)
    assert admitted.weekend_hold_allowed is False and admitted.drawdown_tiers[0].top_tier_only is False
    with pytest.raises(MandateError):replace(admitted,weekend_hold_allowed='false').validate(PlatformCeilings())
