"""TRD-REV51-131: gateway cognition/research/evolution read surface."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "trading"))

from vati.core.events import EventKind, make_event  # noqa: E402
from vati.core.ledger import Ledger  # noqa: E402
from van_gateway.trading import TradingService  # noqa: E402


def test_cognition_without_a_ledger_is_explicitly_unavailable(tmp_path):
    service = TradingService(str(tmp_path / "missing.sqlite"))
    payload = service.cognition()
    assert payload["ledger_available"] is False
    # GAP-F-004. This used to claim SHADOW_LIVE on every host while no provider
    # invoker existed anywhere in production. With no invoker reported, the read
    # model now says so explicitly instead of describing a system that is
    # structurally empty.
    assert payload["authority"]["cognition_invoker"] == "none"
    assert payload["authority"]["invoker_state"] == "MODEL_INVOKER_UNCONFIGURED"
    assert payload["authority"]["cognition_mode"] == "OFFLINE_EVOLUTION_ONLY"
    assert payload["authority"]["live_advisory"] == "DISABLED"
    assert payload["authority"]["live_status"] == "NOT_CLAIMED"
    # The hierarchy is still listed, but as what this build supports rather
    # than as evidence that any of it answered.
    assert payload["authority"]["supported_model_hierarchy"][0] == "fable-5.1"
    assert payload["authority"]["execution_authority"] == (
        "VATI_RISK_AUTHORITY_AND_EXECUTION_ROUTER_ONLY"
    )


def test_cognition_projection_reads_evidence_without_exposing_a_write_path(tmp_path):
    path = tmp_path / "vati.sqlite"
    ledger = Ledger(path)
    ledger.append(make_event(
        EventKind.COGNITIVE_ASSESSMENT,
        "vati-shadow-cognition",
        {
            "assessment_id": "a-1",
            "model_id": "fable-5.1",
            "verdict": "CONCUR",
            "reason_codes": [],
            "confidence": "0.7",
            "produced_ms": 10,
            "seal": "s-1",
        },
        event_time_ms=10, received_time_ms=10, correlation_id="ctx-1",
    ))
    ledger.append(make_event(
        EventKind.RESEARCH_MISSION,
        "vati-research",
        {"mission_id": "m-1", "state": "RUNNING", "hypothesis": "edge drift?"},
        event_time_ms=11, received_time_ms=11, correlation_id="m-1",
    ))
    ledger.append(make_event(
        EventKind.IMPROVEMENT_PROPOSAL,
        "vati-evolution",
        {
            "proposal_id": "p-1", "title": "candidate",
            "live_affecting": True, "affected_paths": ["x"],
        },
        event_time_ms=12, received_time_ms=12, correlation_id="p-1",
    ))
    ledger.close()

    service = TradingService(str(path))
    payload = service.cognition()
    assert payload["ledger_available"] is True
    assert payload["summary"]["assessments"] == 1
    assert payload["summary"]["research_missions"] == 1
    assert payload["summary"]["improvement_proposals"] == 1
    assert payload["models"][0]["model_id"] == "fable-5.1"
    assert payload["authority"]["live_status"] == "NOT_CLAIMED"

    public = {name for name in dir(TradingService) if not name.startswith("_")}
    assert "cognition" in public
    assert not any(
        token in name.lower()
        for name in public
        for token in ("cognition_order", "cognition_submit", "cognition_size")
    )


def test_fastapi_app_registers_cognition_as_get_only():
    # Static route proof avoids booting external services merely to assert the HTTP verb.
    source = (ROOT / "backend" / "van_gateway" / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/v1/trading/cognition")' in source
    assert '@app.post("/v1/trading/cognition")' not in source
    assert '@app.put("/v1/trading/cognition")' not in source
    assert '@app.delete("/v1/trading/cognition")' not in source
