"""Pure directory projection: source policy is never provider qualification."""
import hashlib
import json
import pytest
from pydantic import ValidationError

from backend.tests.test_trading_api import client, _env
from backend.tests.test_trading_oauth_scope import isolated_native_account_state
from van_gateway.trading.account_operations import BROKER_NAMES, OPERATIONS
from van_gateway.trading.broker_directory import BrokerDirectoryResponse, broker_directory


def test_directory_has_each_source_family_and_explicit_unknown_provider_facts():
    result = broker_directory()
    assert result["schema"] == "van.broker-directory/1"
    assert result["execution_authority"] is False
    assert result["freshness"] == "NOT_PROVIDER_READBACK"
    rows = result["families"]
    assert {r["family"] for r in rows} == set(BROKER_NAMES) | {"VFEX", "CEX_SPOT"}
    assert len(rows) == len(BROKER_NAMES) + 2
    expected = {"order_types", "fill_policies", "expiries", "stop_mode", "hedging_netting",
                "minimum_lot", "instruments", "regulator", "account_currencies",
                "minimum_deposit", "open_account_url"}
    for row in rows:
        assert set(row["capabilities"]) == expected
        if row["family"] in BROKER_NAMES:
            assert row["native_broker_kind"] == row["family"]
            assert set(row["operations"]) == set(OPERATIONS)
            assert row["operations_provenance"] == "SOURCE_POLICY_ONLY_NOT_CURRENT_ADMISSION"
        else:
            assert row["native_broker_kind"] is None and row["family_state"] == "REQUIRED_UNADMITTED"
            assert row["operations"] is None and row["linking"]["action"] is None
        for fact in row["capabilities"].values():
            assert fact == {"state": "UNKNOWN", "value": None,
                            "provenance": "NO_ADMITTED_PROVIDER_SOURCE", "freshness": "NOT_OBSERVED"}
    json.dumps(result, allow_nan=False)


def test_source_methods_and_demo_do_not_claim_provider_availability():
    rows = {r["family"]: r for r in broker_directory()["families"]}
    assert rows["DERIV"]["linking"]["action"] == "deriv_oauth_link"
    assert rows["CTRADER"]["linking"]["action"] == "ctrader_link"
    assert rows["MT5_EA"]["linking"]["action"] == "mt5_ea_issue_key"
    assert rows["MT5"]["linking"]["method"] == "WINDOWS_BRIDGE_REGISTRATION"
    assert rows["PAPER"]["linking"]["method"] == "LOCAL_SIMULATION"
    for family in BROKER_NAMES:
        row = rows[family]
        assert row["demo_availability"]["freshness"] == "NOT_PROVIDER_READBACK"
        assert row["operations"]["request_live"]["state"] == "PROVIDER_ADMISSION_REQUIRED"
    assert rows["DERIV"]["demo_availability"]["state"] == "SOURCE_IMPLEMENTED"
    assert rows["PAPER"]["demo_availability"]["state"] == "SOURCE_IMPLEMENTED"
    assert rows["CTRADER"]["demo_availability"]["state"] == "PROVIDER_ADMISSION_REQUIRED"
    assert rows["VFEX"]["linking"]["method"] == "OWNER_TICKET"
    assert rows["CEX_SPOT"]["linking"]["state"] == "REQUIRED_UNQUALIFIED"
    cex = rows["CEX_SPOT"]
    assert cex["canonical_requirements"] == ["VAN-CRYPTO-001", "VAN-CRYPTO-002", "VAN-CRYPTO-013", "VAN-RV-008"]
    assert set(cex["required_versioned_identity"]) == {"api_family", "account_subaccount", "native_product",
                                                        "spot_type", "base", "quote", "network"}
    assert all(fact["state"] == "UNKNOWN" and fact["value"] is None
               for fact in cex["required_versioned_identity"].values())
    for family in ("MT5", "MT5_EA"):
        required = rows[family]["additional_linking_requirements"][0]
        assert required["method"] == "INVESTOR_PASSWORD_READ_ONLY"
        assert required["state"] == "REQUIRED_UNQUALIFIED" and required["action"] is None


def test_returned_records_are_independent_and_inventory_drift_fails_closed(monkeypatch):
    from van_gateway.trading import broker_directory as module
    first = module.broker_directory()
    first["families"][0]["capabilities"]["regulator"]["value"] = "changed"
    assert module.broker_directory()["families"][0]["capabilities"]["regulator"]["value"] is None
    monkeypatch.setattr(module, "BROKER_NAMES", module.BROKER_NAMES | {"UNADMITTED"})
    with pytest.raises(RuntimeError, match="inventory changed"):
        module.broker_directory()


def test_revision_is_stable_and_binds_the_actual_source_projection(monkeypatch):
    from van_gateway.trading import broker_directory as module
    first = module.broker_directory()
    assert first["content_revision"] == module.broker_directory()["content_revision"]
    assert first["content_revision"]["scope"] == "SOURCE_PROJECTION_CONTENT"
    encoded = json.dumps(first["families"], sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert first["content_revision"]["digest"] == hashlib.sha256(encoded).hexdigest()
    original = module.capabilities_for
    def changed(**kwargs):
        result = original(**kwargs)
        if kwargs["broker"] == "PAPER":
            result["edit_local"]["reason"] = "Changed source policy fixture"
        return result
    monkeypatch.setattr(module, "capabilities_for", changed)
    assert module.broker_directory()["content_revision"]["digest"] != first["content_revision"]["digest"]


def test_public_schema_roundtrips_unknown_and_optional_rows_without_changing_revision():
    value = broker_directory()
    serialized = BrokerDirectoryResponse.model_validate(value).model_dump(by_alias=True, exclude_unset=True)
    assert serialized == value
    unknown = serialized['families'][0]['capabilities']['regulator']
    assert 'value' in unknown and unknown['value'] is None
    schema = BrokerDirectoryResponse.model_json_schema(by_alias=True)
    assert 'schema' in schema['properties'] and 'families' in schema['properties']
    with pytest.raises(ValidationError):
        BrokerDirectoryResponse.model_validate({**value, 'execution_authority': True})


@pytest.mark.asyncio
async def test_paired_device_reads_exact_directory_without_native_dispatch(client, tmp_path, monkeypatch):
    ac, app = client
    def forbidden(*args, **kwargs):
        raise AssertionError("read-only directory dispatched native account work")
    monkeypatch.setattr(app.state.onboarding.control, "run", forbidden)
    response = await ac.get('/v1/trading/accounts/brokers')
    assert response.status_code == 200, response.text
    assert response.json() == broker_directory()
    assert len(response.json()['families']) == 8
    assert response.json()['content_revision']['scope'] == 'SOURCE_PROJECTION_CONTENT'
    assert not (tmp_path / 'accounts.json').exists()
    assert not (tmp_path / 'vati.sqlite').exists()


@pytest.mark.asyncio
async def test_unpaired_or_revoked_device_cannot_read_directory(client, tmp_path, monkeypatch):
    ac, app = client
    def forbidden(*args, **kwargs):
        raise AssertionError("denied directory request dispatched native account work")
    monkeypatch.setattr(app.state.onboarding.control, "run", forbidden)
    unpaired = await ac.get('/v1/trading/accounts/brokers', headers={'X-Van-Device-Token': ''})
    assert unpaired.status_code == 401 and 'families' not in unpaired.text
    # A device revoked between ingress authentication and the route's current
    # registered-device check must also be refused by that second boundary.
    original = app.state.auth.require_access_token
    async def revoke_after_ingress(token):
        device = await original(token)
        await app.state.auth.revoke(device.device_id)
        return device
    monkeypatch.setattr(app.state.auth, 'require_access_token', revoke_after_ingress)
    race = await ac.get('/v1/trading/accounts/brokers')
    assert race.status_code == 403 and 'families' not in race.text
    monkeypatch.setattr(app.state.auth, 'require_access_token', original)
    revoked = await ac.get('/v1/trading/accounts/brokers')
    assert revoked.status_code == 401 and 'families' not in revoked.text
    assert not (tmp_path / 'accounts.json').exists()
    assert not (tmp_path / 'vati.sqlite').exists()
