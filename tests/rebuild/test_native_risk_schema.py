"""Actual serialized source fixtures satisfy the declared JSON Schema.

The validator is pinned in tools/rebuild/requirements.lock. These checks
establish representation only, never native identity or financial authority.
"""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT/'trading/vati/contracts/schemas/risk_snapshot.schema.json'
FIXTURES = Path(__file__).parent/'fixtures/native_risk_snapshots_e9cbdd69.json'
ORIGINAL_REQUIRED = {
    'now_unix', 'account_alias', 'account_verified', 'equity', 'balance', 'peak_equity',
    'day_start_equity', 'week_start_equity', 'consecutive_losses', 'open_positions',
    'symbol_contract', 'quote_age_ms', 'max_quote_age_ms', 'broker_connected',
    'reconciliation_ok', 'clock_sync_ok', 'risk_store_ok', 'market_integrity',
    'tier1_event_blackout_active', 'kill_switch_triggers', 'margin_level_pct', 'free_margin',
    'preservation_blocks_new_risk', 'preservation_reason', 'loss_streak_lock',
    'loss_streak_multiplier', 'drawdown_top_state',
}


def validator():
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def current(provider='MT5'):
    return deepcopy(json.loads(FIXTURES.read_text())['snapshots'][provider])


def test_every_original_required_field_and_root_closure_remain_intact():
    schema = json.loads(SCHEMA.read_text())
    assert set(schema['required']) == ORIGINAL_REQUIRED
    assert schema['additionalProperties'] is False
    assert 'native_account_context' not in schema['required']


@pytest.mark.parametrize('provider', ['MT5', 'CTRADER'])
def test_original_basis_reference_preserves_legacy_serialization_and_closed_schema(provider):
    # JSON Schema validation uses its existing declared rebuild dependency.
    # The source trading runtime/suite does not import that documentary tool.
    legacy_body=current(provider)
    assert 'native_risk_basis_ref' not in legacy_body
    schema=json.loads(SCHEMA.read_text())
    assert len(schema['required'])==27 and schema['additionalProperties'] is False
    Draft202012Validator(schema).validate(legacy_body)
    body=deepcopy(legacy_body)
    body['native_risk_basis_ref']='a'*64
    Draft202012Validator(schema).validate(body)
    body['native_risk_basis_ref']='not-a-sealed-ref'
    assert list(Draft202012Validator(schema).iter_errors(body))


@pytest.mark.parametrize('provider', ['MT5', 'CTRADER'])
def test_actual_original_native_context_serializer_output_validates(provider):
    fixture = json.loads(FIXTURES.read_text())
    assert fixture['source_head'] == 'e9cbdd69c9d98688e14b088c19c65e5df80c6e42'
    assert fixture['execution_authority'] is fixture['economic_evidence'] is False
    body = current(provider)
    validator().validate(body)
    assert body['native_account_context']['provider'] == provider


@pytest.mark.parametrize('name', ['legacy_risk_snapshot_b58bb578.json',
                                  'legacy_risk_snapshot_no_margin_74b1749a.json'])
def test_actual_historical_bodies_remain_valid_without_new_source_observations(name):
    original = json.loads((ROOT/'trading/tests/fixtures'/name).read_text())
    body = original['snapshot']
    assert 'native_account_context' not in body
    validator().validate(body)


def test_explicit_unknown_context_is_representable_but_never_a_source_grant():
    body = current()
    body['native_account_context'] = None
    validator().validate(body)


@pytest.mark.parametrize('flag', ['execution_authority', 'risk_capital_qualified'])
@pytest.mark.parametrize('value', [True, 0, 1, 'false', None])
def test_native_identity_cannot_claim_authority_or_coerce_boolean_types(flag, value):
    body = current()
    body['native_account_context'][flag] = value
    with pytest.raises(ValidationError):
        validator().validate(body)


@pytest.mark.parametrize('field,value', [
    ('provider', 'PAPER'), ('provider', 'DERIV'),
    ('physical_account_key', 'native-account:v1:'+'A'*64),
    ('monetary_scope_hash', '0'*63), ('observation_ref', '0'*63),
    ('source_query_ref', None), ('source_mark_json', {}),
    ('source_mark_json', 'x'*16385), ('unearned_owner_grant', True),
])
def test_malformed_native_metadata_or_unknown_fields_are_rejected(field, value):
    body = current()
    body['native_account_context'][field] = value
    with pytest.raises(ValidationError):
        validator().validate(body)


@pytest.mark.parametrize('field', ['provider', 'physical_account_key', 'monetary_scope_hash',
    'account_alias', 'observation_ref', 'source_query_ref', 'source_mark_json',
    'risk_capital_qualified', 'execution_authority'])
def test_present_native_context_retains_every_required_original_source_field(field):
    body = current()
    body['native_account_context'].pop(field)
    with pytest.raises(ValidationError):
        validator().validate(body)


def test_ctrader_cannot_fabricate_an_mt5_query_reference():
    body = current('CTRADER')
    body['native_account_context']['source_query_ref'] = '0'*64
    with pytest.raises(ValidationError):
        validator().validate(body)


def test_current_original_stop_terms_are_typed_without_becoming_a_legacy_requirement():
    body = current()
    validator().validate(body)
    assert body['open_positions'][0]['stop_terms']['tick_value'] == '1.00'
    body['open_positions'][0].pop('stop_terms')
    validator().validate(body)


@pytest.mark.parametrize('damage', ['missing', 'float', 'unknown'])
def test_original_stop_terms_cannot_drop_inputs_accept_floats_or_add_authority(damage):
    body = current()
    terms = body['open_positions'][0]['stop_terms']
    if damage == 'missing': terms.pop('tick_value')
    elif damage == 'float': terms['tick_value'] = 1.0
    else: terms['execution_authority'] = True
    with pytest.raises(ValidationError):
        validator().validate(body)
