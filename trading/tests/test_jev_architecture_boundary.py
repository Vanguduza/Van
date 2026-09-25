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
    assert "TradeIntent" in text

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
