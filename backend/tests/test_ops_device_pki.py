"""Direct-phone expiry is observable independently of the optional trading PKI."""

import pytest

from van_gateway.mtls.pki import DeviceCA, init_ca
from van_gateway.observability.alerts import evaluate
from van_gateway.observability.metrics import MetricsRegistry
from van_gateway.ops.health import collect, ops_facts
from van_gateway.ops.pki import scan_device


def _pki(path, *, days=10):
    init_ca(path)
    DeviceCA(path).issue_server("IP:127.0.0.1", days=days)
    return path


@pytest.mark.asyncio
async def test_direct_certificates_reach_health_and_their_alert_without_mutating_pki(tmp_path):
    path = _pki(tmp_path / "device")
    before = {item.name: item.read_bytes() for item in path.iterdir()}
    health = await collect(device_pki_dir=str(path))
    report = health["device_pki"]
    assert report["configured"] and report["present"]
    assert {item["name"] for item in report["certificates"]} == {"ca", "server"}
    assert report["days_remaining"] in (9, 10)
    assert health["pki"]["present"] is False
    alerts = {item.rule for item in evaluate(MetricsRegistry(), ops_facts=ops_facts(health))}
    assert "DEVICE_PKI_EXPIRING" in alerts
    assert "PKI_EXPIRING" not in alerts
    assert {item.name: item.read_bytes() for item in path.iterdir()} == before


def test_unconfigured_and_configured_but_missing_device_pki_have_distinct_alerts(tmp_path):
    absent = scan_device(None)
    missing = scan_device(tmp_path / "lost")
    assert absent == {"configured": False, "present": False, "days_remaining": None}
    assert missing["configured"] and not missing["present"]
    assert missing["missing"] == ["ca", "server"]
    assert missing["days_remaining"] == -1
    assert not evaluate(MetricsRegistry(), ops_facts=ops_facts({"device_pki": absent}))
    assert {item.rule for item in evaluate(MetricsRegistry(), ops_facts=ops_facts({"device_pki": missing}))} == {"DEVICE_PKI_EXPIRING"}


def test_a_healthy_device_pair_does_not_fire_an_expiry_alert(tmp_path):
    report = scan_device(_pki(tmp_path / "device", days=825))
    assert report["days_remaining"] in (824, 825)
    assert not evaluate(MetricsRegistry(), ops_facts=ops_facts({"device_pki": report}))


def test_ca_expiry_is_monitored_even_when_the_server_certificate_is_fresh(tmp_path, monkeypatch):
    import van_gateway.mtls.pki as pki

    monkeypatch.setattr(pki, "CA_DAYS", 10)
    report = scan_device(_pki(tmp_path / "device", days=825))
    assert report["days_remaining"] in (9, 10)
    statuses = {item["name"]: item["days_remaining"] for item in report["certificates"]}
    assert statuses["server"] > 800
    assert statuses["ca"] in (9, 10)


@pytest.mark.asyncio
async def test_gateway_schedules_direct_expiry_and_exposes_it_on_the_operator_surface(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    import httpx
    from van_gateway.app import create_app
    from van_gateway.config import get_settings

    directory = _pki(tmp_path / "device")
    for key, value in {
        "VAN_DATABASE_PATH": str(tmp_path / "gateway.sqlite3"),
        "VAN_GOOGLE_TOKEN_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_DEVICE_SECRET_FERNET_KEY": Fernet.generate_key().decode(),
        "VAN_MTLS_ENABLED": "true", "VAN_MTLS_DIR": str(directory), "VAN_PKI_DIR": "",
        "VAN_SCHEDULER_ENABLED": "false", "VAN_OBSERVABILITY_TOKEN": "synthetic-observer",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            assert "ops.pki_scan" in app.state.scheduler.jobs
            await app.state.scheduler.run_job(app.state.scheduler.jobs["ops.pki_scan"])
            assert app.state.ops_device_pki["days_remaining"] in (9, 10)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
                response = await client.get("/v1/observability/health", headers={"X-Van-Internal-Token": "synthetic-observer"})
            assert response.status_code == 200, response.text
            assert response.json()["device_pki"]["configured"] is True
    finally:
        get_settings.cache_clear()
