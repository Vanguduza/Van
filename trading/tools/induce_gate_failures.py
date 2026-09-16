"""Verification-discipline probe for the Risk Authority (Rev 2 Part D).

A gate whose failure has not been induced is not known to work. This script
breaks the authority in memory, one invariant at a time, and runs the seeded
property fuzz against each broken copy. Expected: every single-point break
that is not covered by a second, independent check makes the fuzz FAIL; the
control run PASSES. Breaks that are masked by defence-in-depth are broken
together with their backstop to show the fuzz still catches the pair.

Run from the repository root:

    python3 trading/tools/induce_gate_failures.py
"""

from __future__ import annotations

import sys
import types
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "trading"), str(ROOT / "trading" / "tests")]

import vati.risk.authority as authority  # noqa: E402
import vati.risk.sizing as sizing  # noqa: E402
import test_authority_properties as fuzz  # noqa: E402

AUTHORITY_SRC = (ROOT / "trading/vati/risk/authority.py").read_text(encoding="utf-8")
SIZING_SRC = (ROOT / "trading/vati/risk/sizing.py").read_text(encoding="utf-8")

MANDATE_CLAMP = ("        if allowed_risk > m.max_risk_per_trade:\n            allowed_risk = m.max_risk_per_trade\n", "        if False:\n            pass\n")
FINAL_RECHECK = ("        if sized.risk_pct > m.max_risk_per_trade or sized.risk_pct > intent.requested_risk_pct:\n            return rej(", "        if False:\n            return rej(")
HEAT_CHECK = ("        if heat_after > m.max_open_stop_risk:\n            return rej(", "        if False:\n            return rej(")
LEG_CHECK = ("        if hot:\n            return rej(", "        if False:\n            return rej(")
DUP_LATCH = ("        self._seen_keys.add(intent.idempotency_key)\n", "")
KILL_CHECK = ("        if snapshot.kill_switch_triggers:\n            return rej(", "        if False:\n            return rej(")
STALE_CHECK = ("        if not snapshot.data_fresh:\n            return rej(", "        if False:\n            return rej(")
ACCOUNT_CHECK = ("        if not snapshot.account_verified:\n            return rej(", "        if False:\n            return rej(")
MODE_CHECK = ("        if not m.sends_orders():\n            return rej(", "        if False:\n            return rej(")
STOP_REQUIRED = ("                if intent.stop is None:\n                    return rej(", "                if False:\n                    return rej(")
SIZING_RECHECK = ("    if risk_amount > risk_capital:\n        # Cannot happen", "    if False:\n        # Cannot happen")


def _module(name: str, src: str, edits: list[tuple[str, str]]) -> types.ModuleType:
    body = src
    for old, new in edits:
        if old not in body:
            raise SystemExit(f"probe edit no longer matches source: {name}: {old[:50]!r}")
        body = body.replace(old, new)
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    exec(compile(body, name, "exec"), mod.__dict__)
    return mod


def broken_authority(name: str, edits: list[tuple[str, str]], *, sizing_edits: list[tuple[str, str]] | None = None, unclamp: bool = False):
    auth_edits = list(edits)
    if sizing_edits is not None or unclamp:
        sz = _module(f"{name}.sizing", SIZING_SRC, sizing_edits or [])
        if unclamp:
            sz.__dict__["clamp_multiplier"] = lambda v: Decimal(str(v))
            sz.__dict__["Multipliers"].clamped = lambda self: self
        auth_edits.append((
            "from vati.risk.sizing import Multipliers, SizingRejected, size_stake_contract, size_stop_contract",
            f"from {name}.sizing import Multipliers, SizingRejected, size_stake_contract, size_stop_contract",
        ))
    mod = _module(name, AUTHORITY_SRC, auth_edits)
    # Preserve enum/dataclass identity so `is` comparisons in the fuzz measure the gate, not class identity.
    mod.__dict__["Decision"] = authority.Decision
    mod.__dict__["RiskDecision"] = authority.RiskDecision
    return mod.RiskAuthority


def run(label: str, expect_fail: bool) -> bool:
    try:
        fuzz.test_risk_authority_invariants()
        outcome, ok = "fuzz PASSED", not expect_fail
    except AssertionError as exc:
        reason = str(exc).split("RiskDecision(")[0].strip()
        outcome, ok = f"fuzz FAILED ({reason[:40]})", expect_fail
    except Exception as exc:  # noqa: BLE001 — a crash is also a detected failure, reported as such
        outcome, ok = f"fuzz CRASHED ({type(exc).__name__}: fail-closed by exception)", expect_fail
    print(f"{'OK ' if ok else 'BAD'}  {label:<58} {outcome}")
    return ok


def main() -> int:
    original = fuzz.RiskAuthority
    results = []
    cases = [
        ("control: unbroken", [], {}, False),
        ("break: multiplier clamp only (masked by sizing re-check)", [], {"unclamp": True}, False),
        ("break: multiplier clamp + sizing re-check + final re-check", [FINAL_RECHECK], {"unclamp": True, "sizing_edits": [SIZING_RECHECK]}, True),
        ("break: mandate per-trade clamp only (masked by final re-check)", [MANDATE_CLAMP], {}, False),
        ("break: mandate per-trade clamp + final re-check", [MANDATE_CLAMP, FINAL_RECHECK], {}, True),
        ("break: portfolio heat check", [HEAT_CHECK], {}, True),
        ("break: currency-leg check", [LEG_CHECK], {}, True),
        ("break: duplicate-intent latch", [DUP_LATCH], {}, True),
        ("break: kill-switch check", [KILL_CHECK], {}, True),
        ("break: stale-data check", [STALE_CHECK], {}, True),
        ("break: account-verified check", [ACCOUNT_CHECK], {}, True),
        ("break: order-sending-mode check", [MODE_CHECK], {}, True),
        ("break: stop-required check", [STOP_REQUIRED], {}, True),
    ]
    for i, (label, edits, kw, expect_fail) in enumerate(cases):
        fuzz.RiskAuthority = original if not edits and not kw else broken_authority(f"vati.risk._probe{i}", edits, **kw)
        results.append(run(label, expect_fail))
    fuzz.RiskAuthority = original
    bad = results.count(False)
    print(f"\n{len(results) - bad}/{len(results)} probes behaved as expected")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
