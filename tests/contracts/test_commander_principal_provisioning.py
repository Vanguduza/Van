from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_gateway_and_hermes_receive_distinct_commander_principals():
    rebuild = read("deploy/van-trading-core/oci/rebuild-van-trading-core.py")
    hermes = read("deploy/van-trading-core/hermes/register-commander-mcp.sh")
    service = read("deploy/systemd/van-gateway.service")

    assert "commander.token.hermes" in rebuild
    assert "commander.hermes.token" in rebuild
    assert "commander.token.van-gateway" in rebuild
    assert "commander.gateway.token" in rebuild
    assert "trading-commander.env" in rebuild
    assert "VAN_COMMANDER_TOKEN_FILE=/home/ubuntu/.config/van/commander.gateway.token" in rebuild
    assert "EnvironmentFile=-%h/.config/van/trading-commander.env" in service
    assert "TOKEN_FILE" in hermes
    assert "commander.gateway.token" not in hermes


def test_gateway_commander_configuration_is_activated_after_provisioning():
    rebuild = read("deploy/van-trading-core/oci/rebuild-van-trading-core.py")
    assert "systemctl --user restart van-gateway.service" in rebuild
    assert "systemctl --user is-active --quiet van-gateway.service" in rebuild
