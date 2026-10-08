"""Owner decisions 2026-09-29 §1, §4, §5 — the van-browser-core trust zone contract.

Fails if:
  * any van-browser-core unit/env/config file references a credential, socket, DB path or
    env name belonging to the VATI Risk Authority, the Execution Router, broker
    credentials, trading secrets, the Owner Model DB, owner-private Hindsight/OpenViking or
    Project Truth mutation. The forbidden names are derived from the repository's own
    trading-core env files and gateway Settings, not remembered;
  * the zone's workers read any environment variable not declared in the zone's own
    runtime.env.example (so a forbidden name cannot enter through code either);
  * Stagehand has a production placement on van-trading-core, dial-control or
    van-private-core;
  * the Stagehand version identity or model default drifts from the owner decisions;
  * any repository file carries a provider key literal.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ZONE_DIR = ROOT / "deploy" / "van-browser-core"
ZONE = json.loads((ZONE_DIR / "zone.json").read_text(encoding="utf-8"))
TRADING = ROOT / "deploy" / "van-trading-core"

sys.path.insert(0, str(ROOT / "backend"))

RELEASE_COMMIT = "cd7b230778cf92269e4cb90e80d97f5113781c51"
INTEGRITY = "sha512-PJikMBVoaCRh6TFD7GcmeISmsMq4IwUu1BD5FOsGUVDUxrVqZomWa6W6dF+a/zu4xRZu2Z2xX1nXVMDaCuZWsw=="
UNRELEASED_HEAD = "ad2bf12e"


def _env_keys(path: Path) -> set[str]:
    return set(re.findall(r"^([A-Z_][A-Z0-9_]*)=", path.read_text(encoding="utf-8"), re.M))


def _settings_env(field_filter) -> set[str]:
    from van_gateway.config import Settings

    return {f"VAN_{name.upper()}" for name in Settings.model_fields if field_filter(name)}


# ---------------------------------------------------------------- forbidden names, derived
#: Everything the trading core's own env declares: Commander token/TLS, ledger DSN, accounts
#: registry, owner authority keys, trading VEKL token, MT5 pull queue.
TRADING_CORE_ENV = _env_keys(TRADING / "env" / "van-trading-core.env.example")
#: The trading store's secrets (Supabase/Postgres) — every key that is a credential.
TRADING_STORE_SECRETS = {
    k
    for k in _env_keys(TRADING / "supabase" / "env.example")
    if re.search(r"(PASSWORD|SECRET|KEY|TOKEN|JWT)", k)
}
TEMPORAL_BRIDGE_SECRETS = {
    k for k in _env_keys(TRADING / "temporal" / "temporal-runtime.env.example") if "TOKEN" in k
}
#: Gateway Settings fields holding trading-plane, Owner Model DB or owner-authority secrets.
GATEWAY_AUTHORITY_ENV = _settings_env(
    lambda n: n.startswith(("vati_", "van_commander_", "internal_control", "device_", "dial_dev_token"))
    or n in {"database_path", "hermes_bearer_token", "google_token_fernet_key", "device_secret_fernet_key"}
)
#: Broker credential env names used by the trading adapters (verified present below).
BROKER_ENV = {
    "DERIV_API_TOKEN",
    "CTRADER_CLIENT_SECRET",
    "CTRADER_ACCESS_TOKEN",
    "CTRADER_REFRESH_TOKEN",
    "BRIDGE_SIGNING_KEY",
    "BRIDGE_CLIENT_CERT",
    "BRIDGE_CLIENT_KEY",
    "BRIDGE_CA_FILE",
}
#: Project Truth mutation credentials / entrypoints.
PROJECT_TRUTH_ENV = {"GITHUB_TOKEN", "GH_TOKEN"}

FORBIDDEN_ENV = (
    TRADING_CORE_ENV
    | TRADING_STORE_SECRETS
    | TEMPORAL_BRIDGE_SECRETS
    | GATEWAY_AUTHORITY_ENV
    | BROKER_ENV
    | PROJECT_TRUTH_ENV
)

#: Paths, sockets, DB files and code identities of the forbidden authorities.
FORBIDDEN_LITERALS = [
    "/opt/van-trading",
    "/var/lib/van-trading",
    "/run/van-trading",
    "/var/log/van-trading",
    "commander.token",
    "owner_authority_keys.json",
    "accounts.json",
    "van_gateway.sqlite3",
    "vati_ledger",
    "postgres://",
    "127.0.0.1:5432",
    ":9133",
    "docker.sock",
    "van-github-recovery",
    "PROJECT_CANONICAL_STATE",
    "docs/project-state",
    "vati.risk",
    "vati.execution",
    "RiskAuthority",
    "ExecutionRouter",
    "vati-",
    "hermes-gateway",
]
#: Owner-private plane: case-insensitive tokens.
FORBIDDEN_PRIVATE_PLANE = re.compile(r"hindsight|openviking|owner[_-]?model|van-private-core", re.I)


def _zone_config_files() -> list[Path]:
    files = [ZONE_DIR / rel for rel in ZONE["unit_env_config_files"]]
    # Every unit in the package is config, whether or not it was listed.
    files += [p for p in (ZONE_DIR / "systemd").glob("*.service") if p not in files]
    return files


def test_forbidden_names_are_real_repository_names():
    """The list is derived from the repo; a name that no longer exists would test nothing."""
    assert "VAN_COMMANDER_TOKEN_FILE" in TRADING_CORE_ENV
    assert "VAN_COMMANDER_LEDGER" in TRADING_CORE_ENV
    assert "VAN_OWNER_AUTHORITY_KEYS" in TRADING_CORE_ENV
    assert "VAN_ACCOUNTS_REGISTRY" in TRADING_CORE_ENV
    assert "POSTGRES_PASSWORD" in TRADING_STORE_SECRETS
    assert "SERVICE_ROLE_KEY" in TRADING_STORE_SECRETS
    assert "VAN_DATABASE_PATH" in GATEWAY_AUTHORITY_ENV  # Owner Model DB lives in the gateway store
    assert "VAN_VATI_SECRETS_DIR" in GATEWAY_AUTHORITY_ENV
    assert "VAN_INTERNAL_CONTROL_TOKEN" in GATEWAY_AUTHORITY_ENV
    tree = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in list((ROOT / "trading").rglob("*.py")) + list((ROOT / "deploy").rglob("*"))
        if p.is_file() and p.suffix in {".py", ".md", ".sh", ".example", ".env"}
    )
    for name in BROKER_ENV:
        assert name in tree, f"{name} no longer appears in the repository; re-derive the list"
    assert (ROOT / "trading/vati/risk/authority.py").read_text(encoding="utf-8").count("class RiskAuthority")
    assert (ROOT / "trading/vati/execution/router.py").read_text(encoding="utf-8").count("class ExecutionRouter")


@pytest.mark.parametrize("path", _zone_config_files(), ids=lambda p: str(p.relative_to(ZONE_DIR)))
def test_zone_unit_env_config_references_no_forbidden_authority(path):
    text = path.read_text(encoding="utf-8")
    tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text))
    assert not (tokens & FORBIDDEN_ENV), f"{path.name}: {sorted(tokens & FORBIDDEN_ENV)}"
    for literal in FORBIDDEN_LITERALS:
        assert literal not in text, f"{path.name} references {literal!r}"
    assert not FORBIDDEN_PRIVATE_PLANE.search(text), f"{path.name} references the owner-private plane"


def test_zone_workers_read_only_declared_env():
    declared = _env_keys(ZONE_DIR / "runtime.env.example")
    # Harness child-process variables the worker itself sets for browser-harness.
    child = {"VAN_BH_URL", "VAN_BH_LOCATOR", "VAN_BH_SECRET", "VAN_BH_KEY", "VAN_BH_DY", "VAN_BH_DX", "VAN_BH_UPLOAD",
             # Review I5 (unit G6a): the bound node, the task scope and describe-the-focus.
             "VAN_BH_BINDING", "VAN_BH_SCOPE", "VAN_BH_FOCUS",
             # Unit G9c: the network-effect guard's policy (mutating flag + task scope).
             "VAN_BH_NETGUARD", "VAN_BH_NETGUARD_STATE"}
    # Explicit development-only escapes, refused in production by the workers themselves
    # (unit G12: the egress proxy exits when VAN_EGRESS_TEST_* is set in a trust zone).
    allowed = declared | child | {"VAN_BROWSER_HISTORICAL_DEV_ONLY", "VAN_EGRESS_TEST_RESOLVE",
                                  "VAN_EGRESS_TEST_UPSTREAM_CAFILE"}
    harness = (ZONE_DIR / "browser" / "harness_service.py").read_text(encoding="utf-8")
    harness += (ZONE_DIR / "browser" / "egress_proxy.py").read_text(encoding="utf-8")
    stagehand = (ZONE_DIR / "browser" / "stagehand_service.mjs").read_text(encoding="utf-8")
    read = set(re.findall(r'os\.(?:getenv|environ\.get)\(\s*"([A-Z0-9_]+)"', harness))
    read |= set(re.findall(r'os\.environ\["([A-Z0-9_]+)"\]', harness))
    assert {"VAN_EGRESS_FENCE_KEY_FILE", "VAN_BROWSER_EGRESS_CONTROL_SOCKET"} <= read
    read |= set(re.findall(r"process\.env\.([A-Z0-9_]+)", stagehand))
    assert read, "env-read scan found nothing; the instrument is broken"
    assert read <= allowed, sorted(read - allowed)
    assert not (read & FORBIDDEN_ENV)
    for text in (harness, stagehand):
        for literal in ("/opt/van-trading", "/var/lib/van-trading", "vati.", "postgres://"):
            assert literal not in text


# ---------------------------------------------------------------- placement
def _stagehand_units() -> list[Path]:
    return [
        p
        for p in (ROOT / "deploy").rglob("*.service")
        if "stagehand_service.mjs" in p.read_text(encoding="utf-8")
    ]


def test_only_van_browser_core_has_a_production_stagehand_unit():
    units = _stagehand_units()
    assert units, "no Stagehand unit found; the instrument is broken"
    for unit in units:
        text = unit.read_text(encoding="utf-8")
        if unit.is_relative_to(ZONE_DIR):
            assert "ConditionPathExists=/etc/van-browser-core/zone" in text
            assert "ExecStartPre=/usr/bin/grep -qx van-browser-core /etc/van-browser-core/zone" in text
            continue
        # Anything else is historical and must be development-only, never production.
        assert unit.is_relative_to(TRADING), f"Stagehand unit outside the known placements: {unit}"
        assert '"$$VAN_BROWSER_HISTORICAL_DEV_ONLY" = 1' in text, unit
        assert "HISTORICAL DEV-ONLY" in text, unit


@pytest.mark.parametrize("zone_dir", ["van-trading-core", "dial-control", "van-private-core"])
def test_forbidden_zone_packages_cannot_install_stagehand_for_production(zone_dir):
    base = ROOT / "deploy" / zone_dir
    if not base.exists():
        return
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix not in {".sh", ".service", ".example", ".yml", ".yaml", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "stagehand" not in text.lower() or path.name == "package-lock.json":
            continue
        # Only the historical dev-only package may mention it, and only behind the guard.
        assert zone_dir == "van-trading-core", f"{path} mentions Stagehand in {zone_dir}"
        assert "VAN_BROWSER_HISTORICAL_DEV_ONLY" in text or "stagehand_not_on_trading_core" in text, path


def test_historical_bootstrap_refuses_without_the_dev_only_flag(tmp_path):
    script = TRADING / "browser" / "bootstrap-browser-runtime.sh"
    text = script.read_text(encoding="utf-8")
    guard = text.index('if [[ "${VAN_BROWSER_HISTORICAL_DEV_ONLY:-}" != 1 ]]')
    assert guard < text.index("npm --prefix")
    assert guard < text.index("systemctl enable")
    # Run the guard itself (as a non-root check would stop first, stub id).
    stub = tmp_path / "id"
    stub.write_text("#!/bin/sh\necho 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin"}
    proc = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 48, proc.stderr
    assert "historical dev-only" in proc.stderr
    proc = subprocess.run(
        ["bash", str(script)],
        env={**env, "VAN_BROWSER_HISTORICAL_DEV_ONLY": "1", "VAN_ENV": "production"},
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 49, proc.stderr


def test_trading_core_bootstrap_does_not_install_the_browser_runtime_in_production():
    text = (TRADING / "bootstrap.sh").read_text(encoding="utf-8")
    call = text.index('bash "$HERE/browser/bootstrap-browser-runtime.sh"')
    guard = text.rindex('if [[ "${VAN_BROWSER_HISTORICAL_DEV_ONLY:-}" == 1 ]]', 0, call)
    assert guard < call
    assert "VAN_VEKL_WORKER_HOST is required for complete production bootstrap" not in text
    assert "stagehand_not_on_trading_core" in (TRADING / "qualify.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("zone", ["van-trading-core", "dial-control", "van-private-core"])
def test_gateway_placement_gate_refuses_forbidden_zones(tmp_path, zone):
    from van_gateway.automation.placement import stagehand_production_enabled
    from van_gateway.config import Settings

    pki = {}
    for field in ("browser_core_ca_file", "browser_core_client_cert_file", "browser_core_client_key_file"):
        f = tmp_path / field
        f.write_text("x", encoding="utf-8")
        pki[field] = str(f)
    s = Settings(
        browser_enabled=True,
        browser_stagehand_zone=zone,
        browser_stagehand_base_url="https://10.77.0.6:9443/stagehand",
        **pki,
    )
    health = {"ok": True, "trust_zone": zone, "runtime_version": "4.1.0",
              "model_name": "anthropic/claude-sonnet-5", "model_key_present": True,
              "provider_key_in_browser_memory": False, "direct_agent_loop": False,
              "model_self_selection": False}
    assert stagehand_production_enabled(s, worker_health=health) == (
        False, f"STAGEHAND_PLACEMENT_FORBIDDEN:{zone}")


def test_worker_refuses_forbidden_zones_at_startup():
    text = (ZONE_DIR / "browser" / "stagehand_service.mjs").read_text(encoding="utf-8")
    assert 'if (TRUST_ZONE !== VAN_BROWSER_CORE && !HISTORICAL_DEV_ONLY)' in text
    assert 'new Set(["van-trading-core", "dial-control", "van-private-core"])' in text
    assert "provider_key_in_browser_memory: true" in text


def test_edge_is_the_only_cross_zone_listener_and_exposes_no_stagehand_actuation():
    caddy = (ZONE_DIR / "edge" / "Caddyfile").read_text(encoding="utf-8")
    assert "mode require_and_verify" in caddy
    assert "trust_pool file /etc/van-browser-core/pki/ca.crt" in caddy
    ops = re.search(r"@stagehand_ops \{(.*?)\}", caddy, re.S).group(1)
    assert "/stagehand/act" not in ops and "/stagehand/agent" not in ops
    env = (ZONE_DIR / "runtime.env.example").read_text(encoding="utf-8")
    assert "VAN_STAGEHAND_BIND=127.0.0.1" in env and "VAN_HARNESS_BIND=127.0.0.1" in env
    ids = [i["id"] for i in ZONE["cross_zone_interfaces"]]
    assert ids == ["BC-IF-1", "BC-IF-2", "BC-IF-3", "BC-IF-4"]


# ---------------------------------------------------------------- version and model
def test_stagehand_release_identity():
    pkg = json.loads((ZONE_DIR / "browser" / "package.json").read_text(encoding="utf-8"))
    assert pkg["dependencies"]["@browserbasehq/stagehand"] == "4.1.0"
    lock = json.loads((ZONE_DIR / "browser" / "package-lock.json").read_text(encoding="utf-8"))
    entry = lock["packages"]["node_modules/@browserbasehq/stagehand"]
    assert (entry["version"], entry["integrity"]) == ("4.1.0", INTEGRITY)
    assert ZONE["stagehand_release"]["upstream_release_commit"] == RELEASE_COMMIT
    for path in (ZONE_DIR / "README.md", ZONE_DIR / "bootstrap.sh", ZONE_DIR / "runtime.env.example",
                 ZONE_DIR / "browser" / "stagehand_service.mjs",
                 ROOT / "docs/project-state/VAN_BROWSER_CORE_MIGRATION_20260929.md"):
        text = path.read_text(encoding="utf-8")
        assert RELEASE_COMMIT in text or "cd7b2307" in text, path
        # ad2bf12e may be named only to say it is NOT 4.1.0.
        for line in text.splitlines():
            if UNRELEASED_HEAD in line:
                assert re.search(r"\bnot\b|unreleased", line, re.I), f"{path}: {line}"


def test_model_is_named_and_no_repository_file_holds_a_provider_key():
    env = (ZONE_DIR / "runtime.env.example").read_text(encoding="utf-8")
    assert "VAN_STAGEHAND_MODEL_PROVIDER=anthropic" in env
    assert "VAN_STAGEHAND_MODEL_NAME=claude-sonnet-5" in env
    assert "VAN_STAGEHAND_MODEL_KEY_REF=secretref://browser/stagehand-model" in env
    from van_gateway.config import Settings

    s = Settings()
    assert (s.browser_stagehand_model_provider, s.browser_stagehand_model_name) == ("anthropic", "claude-sonnet-5")
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    key_re = re.compile(rb"sk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_-]{20,}")
    offenders = []
    for rel in tracked.split(b"\0"):
        if not rel:
            continue
        p = ROOT / rel.decode()
        if not p.is_file() or p.stat().st_size > 5_000_000:
            continue
        if key_re.search(p.read_bytes()):
            offenders.append(rel.decode())
    assert not offenders, offenders


# ---------------------------------------------------------------- egress (unit G12)
def test_zone_declares_the_egress_proxy_and_firewall_it_ships():
    """Owner answers 2026-09-30 after review I7: egress proxy and UDP firewall in zone."""
    egress = ZONE["egress"]
    for rel in (egress["proxy"]["code"], egress["proxy"]["unit"], egress["firewall"]["ruleset"]):
        assert (ZONE_DIR / rel).is_file(), rel
    for rel in ("systemd/van-browser-egress.service", "systemd/van-browser-core-firewall.service",
                "firewall/van-browser-core.nft"):
        assert rel in ZONE["unit_env_config_files"], rel
    proxy = (ZONE_DIR / egress["proxy"]["code"]).read_text(encoding="utf-8")
    for line in egress["proxy"]["refuses"]:
        for code in re.findall(r"EGRESS_[A-Z_]+", line):
            assert f'"{code}"' in proxy, code
    assert "CONNECT host allowlist" in egress["proxy"]["design"] and "wss://" in egress["proxy"]["design"]
    assert "never copied off the host" in egress["proxy"]["key_handling"]
    limits = " ".join(egress["remaining_limits"])
    assert "unverified" in limits.lower() and "DNS" in limits
    # The production gate it names exists and the migration record carries the design.
    assert (ROOT / "docs/decisions/VAN-BROWSER-CORE-EGRESS-001.yaml").is_file()
    assert "VAN-BROWSER-CORE-EGRESS-001.yaml" in egress["production_gate"]
    migration = (ROOT / "docs/project-state/VAN_BROWSER_CORE_MIGRATION_20260929.md").read_text(encoding="utf-8")
    assert "## 8. Egress proxy and zone firewall" in migration and "CONNECT host allowlist" in migration
    bc4 = next(i for i in ZONE["cross_zone_interfaces"] if i["id"] == "BC-IF-4")
    assert "egress proxy" in bc4["transport"] and "firewall" in bc4["transport"]
    # The Harness puts the proxy flags on Chromium's command line (and nothing else changes it).
    # Unit G13: through the single argv assembler (G11), so --disable-features stays merged.
    harness = (ZONE_DIR / "browser" / "harness_service.py").read_text(encoding="utf-8")
    assert harness.count("egress_proxy_flags(self.alias)") == 1
    assert harness.count("chromium_argv(self.profile_dir, extra=egress_proxy_flags(self.alias)),") == 1
    for flag in ("--proxy-bypass-list=<-loopback>", "--ignore-certificate-errors-spki-list=", "--disable-quic"):
        assert flag in harness
