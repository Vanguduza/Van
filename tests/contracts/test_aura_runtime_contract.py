"""Aura Rev 2 (CF-D-08): the shipping aura stays inside its checked-in runtime contract."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools.character_forge import build_reference_pack as pack

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = yaml.safe_load((ROOT / "visual-authority/character-forge/aura/AURA_RUNTIME_CONTRACT.yaml").read_text(encoding="utf-8"))
VIS = ROOT / "android/app/src/main/java/com/dial/van/visual"


def _consts(path: Path) -> dict[str, float]:
    text = path.read_text(encoding="utf-8")
    out = {}
    for name, value in re.findall(r"const val (\w+)\s*=\s*([-0-9._]+)[fL]?\b", text):
        out[name] = float(value.replace("_", ""))
    return out


def _tokens() -> dict[str, str]:
    text = (VIS / "VanGlassTokens.kt").read_text(encoding="utf-8")
    return {m.group(1): "#" + m.group(2)[2:] for m in re.finditer(r"const val (ACCENT_\w+) = 0x([0-9A-Fa-f]{8})", text)}


def _trade_specs() -> dict[str, dict]:
    text = (VIS / "VanTradeSemantic.kt").read_text(encoding="utf-8")
    body = text[text.index("fun auraFor("):text.index("fun durableStateFor(")]
    rows = {}
    for names, args in re.findall(r"((?:VanTradeSemantic\.\w+,?\s*)+) -> idle\.copy\((.*?)\n            \)", body, re.S):
        values = {k: float(v) for k, v in re.findall(r"\b(intensity|arcActivity|sparkRate|deformation|envelopeRadiusScale) = ([0-9.]+)f", args)}
        colour = re.search(r"semanticColor = VanGlassTokens\.(\w+)", args)
        values["semantic"] = colour.group(1) if colour else None
        for name in re.findall(r"VanTradeSemantic\.(\w+)", names):
            rows[name] = values
    return rows


def _within(value: float, bounds) -> bool:
    return bounds[0] - 1e-9 <= value <= bounds[1] + 1e-9


def test_planner_constants_stay_inside_the_contract():
    consts = _consts(VIS / "VanFlameAura.kt")
    for name, bounds in CONTRACT["planner_bounds"].items():
        assert name in consts, f"{name} is bounded by the contract but missing from VanFlameAura.kt"
        assert _within(consts[name], bounds), f"{name}={consts[name]} outside {bounds}"


def test_every_state_field_stays_inside_the_contract():
    table = pack.aura_table()["states"]
    b = CONTRACT["spec_bounds"]
    for state, row in table.items():
        assert _within(row["intensity"], b["intensity"]), state
        assert _within(row["arc"], b["arcActivity"]), state
        assert _within(row["spark"], b["sparkRate"]), state
        assert _within(row["deform"], b["deformation"]), state
        assert _within(row["envelope_scale"], b["envelopeScale"]), state


def test_state_palette_matches_the_contract():
    table = pack.aura_table()["states"]
    tokens = _tokens()
    for state, token in CONTRACT["state_palette"].items():
        expected = None if token is None else tokens[token]
        assert table[state]["semantic_colour"] == expected, f"{state}: {table[state]['semantic_colour']} != {token}"


def test_trade_families_stay_inside_the_contract_and_keep_their_energy_order():
    rows = _trade_specs()
    b = CONTRACT["spec_bounds"]
    for family, token in CONTRACT["trade_palette"].items():
        row = rows[family]
        assert row["semantic"] == token, f"{family} colour {row['semantic']} != {token}"
        for field, key in (("intensity", "intensity"), ("arcActivity", "arcActivity"), ("sparkRate", "sparkRate"), ("deformation", "deformation")):
            assert field in row, f"{family} has no {field}: trade families must set their own flame energy"
            assert _within(row[field], b[key]), f"{family}.{field}={row[field]}"
    ops = {">": lambda a, c: a > c}
    for left, op, right in CONTRACT["trade_energy_rules"]:
        lf, lk = left.split(".")
        rf, rk = right.split(".")
        assert ops[op](rows[lf][lk], rows[rf][rk]), f"{left} {op} {right} violated"


def test_silhouette_and_sampler_settings_stay_inside_the_contract():
    square = _consts(VIS / "VanSilhouette.kt")["SQUARE"]
    assert _within(square, CONTRACT["silhouette"]["square_grid"])
    sampler = _consts(VIS / "VanRiveAvatar.kt")
    assert _within(sampler["GRID"], CONTRACT["silhouette"]["rive_sample_grid"])
    assert _within(sampler["INTERVAL_NANOS"] / 1e6, CONTRACT["silhouette"]["rive_sample_interval_ms"])


def test_no_line_geometry_reaches_the_plan():
    plan = (VIS / "VanAuraPlan.kt").read_text(encoding="utf-8")
    body = plan[plan.index("fun plan("):plan.index("private fun zoneA(")]
    assert "VanFieldGeometryEngine.build" not in body, "CF-D-06-REV1: the plan must not draw field strands again"
    assert "VanAuraOp.Polyline(" not in body and "VanAuraOp.Quad(" not in body


def test_always_on_trade_reader_stays_inside_the_contract():
    reader = CONTRACT["trade_reader"]
    publisher = ROOT / reader["source"]
    consts = _consts(publisher)
    assert _within(consts["POLL_MS"], reader["poll_ms"]), consts["POLL_MS"]
    overlay = (ROOT / "android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt").read_text(encoding="utf-8")
    # The overlay holds the reader only while it animates, and always lets go on destroy.
    assert "OverlayTradeAura.hold(application, OverlayVisibilityPolicy.target(visibility) == OverlayLifecycleTarget.ANIMATING)" in overlay
    assert "OverlayTradeAura.hold(application, visible = false)" in overlay
    route = (ROOT / "android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt").read_text(encoding="utf-8")
    assert "VanTradeAuraPublisher.acquire(TRADING_SCREEN_HOLDER, repo, strict = true)" in route
