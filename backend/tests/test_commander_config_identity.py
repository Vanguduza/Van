from van_gateway.config import Settings


def test_commander_settings_use_single_van_environment_prefix(monkeypatch):
    monkeypatch.setenv("VAN_COMMANDER_URL", "https://trading.test:9133")
    monkeypatch.setenv("VAN_COMMANDER_TOKEN_FILE", "/run/van/commander.gateway.token")
    monkeypatch.setenv("VAN_COMMANDER_CA_FILE", "/run/van/ca.crt")
    settings = Settings()
    assert settings.van_commander_url == "https://trading.test:9133"
    assert settings.van_commander_token_file == "/run/van/commander.gateway.token"
    assert settings.van_commander_ca_file == "/run/van/ca.crt"


def test_legacy_double_prefix_is_accepted_but_not_required(monkeypatch):
    monkeypatch.delenv("VAN_COMMANDER_URL", raising=False)
    monkeypatch.setenv("VAN_VAN_COMMANDER_URL", "https://legacy.test:9133")
    assert Settings().van_commander_url == "https://legacy.test:9133"
