from __future__ import annotations

from pathlib import Path
import re


TRADING_ROOT = Path(__file__).resolve().parents[1]
VATI_ROOT = TRADING_ROOT / "vati"
ALLOWED_JEV_FILE = VATI_ROOT / "cognition" / "invokers.py"


def _jev_mentions(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    return [
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if re.search(r"\bjev\b", line, flags=re.IGNORECASE)
    ]


def test_jev_is_absent_from_all_deterministic_vati_paths():
    offenders: dict[str, list[int]] = {}
    for path in VATI_ROOT.rglob("*.py"):
        mentions = _jev_mentions(path)
        if not mentions:
            continue
        if path.resolve() != ALLOWED_JEV_FILE.resolve():
            offenders[str(path.relative_to(TRADING_ROOT))] = mentions
    assert offenders == {}


def test_only_active_cognition_prompt_can_expose_jev_to_the_reasoning_llm():
    text = ALLOWED_JEV_FILE.read_text(encoding="utf-8")
    assert "Optional Jev System-1 support" in text
    assert "jev_registered_batch" in text
    assert "subordinate evidence only" in text
    assert "Never call Jev as an independent/background trading loop" in text
    assert "risk_multiplier" in text
    assert "\"order\"" in text
    assert "mandate or execution" in text

    # No SDK/client/import lives in VATI. Jev is reached only as a bounded Hermes
    # tool made available to an already-running cognition model.
    assert not re.search(r"^\s*(?:from|import)\s+.*jev", text, flags=re.IGNORECASE | re.MULTILINE)
    assert "http://127.0.0.1:6791" not in text
    assert "/v1/judgments" not in text


def test_broker_risk_regime_and_meta_labeler_boundaries_have_zero_jev_references():
    forbidden_names = {
        "meta_labeler.py",
        "regimes.py",
        "risk.py",
        "risk_authority.py",
        "execution.py",
        "broker.py",
        "broker_adapter.py",
    }
    offenders = {}
    for path in VATI_ROOT.rglob("*.py"):
        if path.name not in forbidden_names:
            continue
        mentions = _jev_mentions(path)
        if mentions:
            offenders[str(path.relative_to(TRADING_ROOT))] = mentions
    assert offenders == {}


# ---------------------------------------------------------------------------------------
# Programme B — the browser path. Jev browser proposals and every other browser lane stay
# on the VAN side of the boundary: nothing in the Browser Fabric or the Jev client can
# reach VATI order entry, sizing or risk, and VATI reaches neither of them.

import ast  # noqa: E402
import asyncio  # noqa: E402

REPO_ROOT = TRADING_ROOT.parent
VAN_BROWSER = REPO_ROOT / "backend" / "van_gateway" / "browser"
VAN_JEV = REPO_ROOT / "backend" / "van_gateway" / "jev"
TRADING_MODULE_PREFIXES = ("vati", "trading", "van_gateway.trading")
VAN_BROWSER_JEV_PREFIXES = ("van_gateway.browser", "van_gateway.jev", "van_gateway.computer_use")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_browser_fabric_and_jev_client_import_nothing_from_trading():
    offenders = {}
    for root in (VAN_BROWSER, VAN_JEV):
        for path in root.rglob("*.py"):
            bad = {m for m in _imported_modules(path) if m.startswith(TRADING_MODULE_PREFIXES)}
            if bad:
                offenders[str(path.relative_to(REPO_ROOT))] = sorted(bad)
    assert offenders == {}


def test_vati_imports_nothing_from_the_browser_fabric_or_jev():
    offenders = {}
    for path in VATI_ROOT.rglob("*.py"):
        bad = {m for m in _imported_modules(path) if m.startswith(VAN_BROWSER_JEV_PREFIXES)}
        if bad:
            offenders[str(path.relative_to(TRADING_ROOT))] = sorted(bad)
    assert offenders == {}


def test_vati_execution_and_risk_have_no_browser_or_jev_entry():
    offenders = {}
    for package in ("execution", "risk"):
        for path in (VATI_ROOT / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            hits = [
                n for n, line in enumerate(text.splitlines(), start=1)
                if re.search(r"\b(jev|playwright|stagehand|interaction_router|browser_harness)\b", line, re.IGNORECASE)
            ]
            if hits:
                offenders[str(path.relative_to(TRADING_ROOT))] = hits
    assert offenders == {}


def test_router_refuses_a_trading_protected_page_before_any_lane():
    from van_gateway.browser.interaction_router import (
        InteractionRequest,
        InteractionRouter,
        InteractionTarget,
        RouteStatus,
    )

    class _Lease:
        async def assert_may_actuate(self, **_):
            return None

    class _Protected:
        def classify_observation(self, observation):
            return {"eligibility": "TRADING_PROTECTED", "reasons": ["broker_order_ticket"],
                    "data_class": None, "jev_payload": None}

    calls = []

    class _Anything:
        async def propose_action(self, payload):
            calls.append("jev")
            return {}

        async def act(self, request):
            calls.append("stagehand")
            return {}

        async def execute(self, step, *, request):
            calls.append("execute")
            return {}

    lane = _Anything()
    router = InteractionRouter(leases=_Lease(), eligibility=_Protected(), jev=lane, stagehand=lane, executor=lane)
    result = asyncio.run(router.route(InteractionRequest(
        session_id="s", control_lease_id="l", control_generation=1, observation={},
        observation_epoch="e", targets=(InteractionTarget("t_buy", "button", "Buy"),),
    )))
    assert result.status is RouteStatus.POLICY_REFUSED
    assert calls == []
