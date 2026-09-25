"""GAP-F-004: the shadow cognition provider invoker and its injection point.

The audit found `ShadowCognitionRuntime(invoker=...)` with no production caller
and no configuration anywhere, so the entire cognition package abstained
`MODEL_UNAVAILABLE` forever. These tests pin both halves of the acceptance
criterion: with an invoker configured `wake()` records a real assessment;
without one the abstention is explicit — and the deterministic RiskAuthority
decision is untouched either way.
"""

from __future__ import annotations

import json
import os
import stat
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import intent, mandate_dict, snapshot
from vati.cognition.contracts import AssessmentRejected, ModelRole, Verdict, normalise
from vati.cognition.invokers import (
    CONTRACT_VERSION,
    INVOKER_MODES,
    UNCONFIGURED_STATE,
    CognitionConfig,
    CognitionConfigError,
    HermesRunInvoker,
    HttpJsonInvoker,
    InvokerRefused,
    NullInvoker,
    build_invoker,
    resolve_credential,
)
from vati.cognition.providers import ProviderLease
from vati.cognition.runtime import ShadowCognitionRuntime
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.risk import RiskAuthority, TradingMandate

LEASE = ProviderLease(
    lease_id="lease-1", model_id="fable-5.1", role=ModelRole.PRIMARY,
    control_profile="vati-controls/5.1.0", acquired_ms=1_000,
    deadline_ms=61_000, attempt=1,
)
CONTEXT = {"context_hash": "ctx-abc", "decision_point": {"symbol": "EURUSD"}}


class FakeTransport:
    """One scripted response per call, plus a record of what was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, *, url, headers, body, timeout_s):
        self.calls.append({
            "url": url, "headers": dict(headers),
            "body": json.loads(body.decode()), "timeout_s": timeout_s,
        })
        if not self.responses:
            raise AssertionError("transport called more times than scripted")
        status, payload = self.responses.pop(0)
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return status, raw


def _envelope(**overrides):
    body = {
        "verdict": "CONCUR", "reason_codes": [], "risk_multiplier": "1",
        "confidence": "0.7", "narrative": "the deterministic path is sound",
        "horizon_ms": 3_600_000,
    }
    body.update(overrides)
    return {"contract_version": CONTRACT_VERSION, "assessment": body}


# --- configuration --------------------------------------------------------

def test_default_configuration_builds_no_invoker():
    """The default must change nothing: this is what every existing host has."""
    cfg = CognitionConfig()
    assert cfg.invoker == "none" and not cfg.configured
    assert build_invoker(cfg) is None
    assert cfg.read_model()["state"] == UNCONFIGURED_STATE
    assert cfg.read_model()["cognition_invoker"] == "none"


def test_every_declared_mode_is_known():
    assert set(INVOKER_MODES) == {"none", "http_json", "hermes_run"}


def test_unknown_invoker_mode_is_refused_not_defaulted():
    with pytest.raises(CognitionConfigError, match="unknown cognition invoker"):
        CognitionConfig(invoker="whatever_you_like")


def test_a_configured_invoker_without_an_endpoint_is_refused():
    with pytest.raises(CognitionConfigError, match="requires an endpoint"):
        CognitionConfig(invoker="http_json")


def test_an_unrecognised_config_key_is_refused():
    """A silently ignored key is an operator believing cognition is wired."""
    with pytest.raises(CognitionConfigError, match="unknown cognition config fields"):
        CognitionConfig.from_mapping({"invoker": "none", "endpont": "typo"})


def test_config_round_trips_from_the_session_mapping():
    cfg = CognitionConfig.from_mapping(
        {"invoker": "http_json", "endpoint": "https://x/y", "timeout_s": 3,
         "model_id": "fable-5.1"},
        secrets_dir="/opt/secrets")
    assert cfg.configured and cfg.timeout_s == 3 and cfg.secrets_dir == "/opt/secrets"
    assert cfg.read_model()["state"] == "CONFIGURED"


# --- credentials ----------------------------------------------------------

def test_a_literal_credential_is_refused():
    """Credentials are references. A value in configuration is the defect."""
    with pytest.raises(CognitionConfigError, match="is not a reference"):
        resolve_credential("sk-live-abcdef0123456789")


def test_env_reference_resolves_and_missing_one_fails_closed(monkeypatch):
    monkeypatch.setenv("VAN_TEST_COGNITION_TOKEN", "t0ken")
    assert resolve_credential("env://VAN_TEST_COGNITION_TOKEN") == "t0ken"
    monkeypatch.delenv("VAN_TEST_COGNITION_TOKEN")
    with pytest.raises(CognitionConfigError, match="is not set"):
        resolve_credential("env://VAN_TEST_COGNITION_TOKEN")


def test_secretref_resolves_through_the_broker_token_mechanism(tmp_path):
    """Same 0600 secrets file the broker adapters already use."""
    secrets_dir = tmp_path / "vati_secrets"
    (secrets_dir / "cognition").mkdir(parents=True)
    path = secrets_dir / "cognition" / "primary"
    path.write_text("API_KEY=abc123\nOTHER=zzz\n", encoding="utf-8")
    path.chmod(0o600)
    assert resolve_credential(
        "secretref://cognition/primary#API_KEY", secrets_dir=str(secrets_dir)) == "abc123"


def test_a_loosely_permissioned_secrets_file_is_refused(tmp_path):
    path = tmp_path / "primary"
    path.write_text("TOKEN=abc\n", encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(CognitionConfigError, match="0600"):
        resolve_credential("file://" + str(path) + "#TOKEN")


def test_secretref_without_a_secrets_directory_is_refused():
    with pytest.raises(CognitionConfigError, match="secrets directory"):
        resolve_credential("secretref://cognition/primary#TOKEN")


# --- NullInvoker ----------------------------------------------------------

def test_null_invoker_refuses_with_model_unavailable():
    with pytest.raises(InvokerRefused) as exc:
        NullInvoker()(LEASE, CONTEXT)
    assert exc.value.code == "MODEL_UNAVAILABLE"


# --- HttpJsonInvoker ------------------------------------------------------

def test_http_invoker_sends_the_declared_request_and_returns_the_assessment():
    transport = FakeTransport([(200, _envelope())])
    invoker = HttpJsonInvoker(
        endpoint="https://cognition.internal/assess", transport=transport,
        credential="secret-value", timeout_s=7)
    raw = invoker(LEASE, CONTEXT)

    sent = transport.calls[0]
    assert sent["url"] == "https://cognition.internal/assess"
    assert sent["timeout_s"] == 7
    assert sent["headers"]["Authorization"] == "Bearer secret-value"
    assert sent["body"]["contract_version"] == CONTRACT_VERSION
    assert sent["body"]["context_hash"] == "ctx-abc"
    assert sent["body"]["role"] == "PRIMARY"

    assessment = normalise(
        raw, model_id="fable-5.1", role=ModelRole.PRIMARY,
        context_hash="ctx-abc", now_ms=2_000)
    assert assessment.verdict is Verdict.CONCUR
    assert assessment.risk_multiplier == Decimal("1")
    assert assessment.seal_ok()


def test_http_invoker_makes_exactly_one_attempt():
    """Retries are refused: the market has moved and the budget would be wrong."""
    transport = FakeTransport([(503, {"error": "busy"})])
    invoker = HttpJsonInvoker(endpoint="https://x/y", transport=transport)
    with pytest.raises(InvokerRefused) as exc:
        invoker(LEASE, CONTEXT)
    assert exc.value.code == "HTTP_STATUS"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("status,payload,code", [
    (500, {"error": "boom"}, "HTTP_STATUS"),
    (200, b"<html>gateway error</html>", "RESPONSE_MALFORMED"),
    (200, ["not", "an", "object"], "RESPONSE_MALFORMED"),
    (200, {"contract_version": "some-other/1.0.0", "assessment": {}}, "CONTRACT_VERSION"),
    (200, {"contract_version": CONTRACT_VERSION}, "ENVELOPE_MALFORMED"),
])
def test_http_invoker_fails_closed_on_every_malformed_answer(status, payload, code):
    invoker = HttpJsonInvoker(
        endpoint="https://x/y", transport=FakeTransport([(status, payload)]))
    with pytest.raises(InvokerRefused) as exc:
        invoker(LEASE, CONTEXT)
    assert exc.value.code == code


def test_an_assessment_carrying_order_fields_is_refused_by_the_contract():
    """INV-AUTH-001 / INV-EXEC-001 as a parsing rule, end to end."""
    invoker = HttpJsonInvoker(
        endpoint="https://x/y",
        transport=FakeTransport([(200, _envelope(approved_size="3.5"))]))
    raw = invoker(LEASE, CONTEXT)
    with pytest.raises(AssessmentRejected, match="ORDER_FIELDS_PRESENT"):
        normalise(raw, model_id="m", role=ModelRole.PRIMARY,
                  context_hash="ctx-abc", now_ms=1)


def test_a_multiplier_above_one_is_refused_not_clamped():
    invoker = HttpJsonInvoker(
        endpoint="https://x/y",
        transport=FakeTransport([(200, _envelope(
            verdict="REDUCE", reason_codes=["EVIDENCE_THIN"], risk_multiplier="1.4"))]))
    with pytest.raises(AssessmentRejected, match="MULTIPLIER_ABOVE_ONE"):
        normalise(invoker(LEASE, CONTEXT), model_id="m", role=ModelRole.PRIMARY,
                  context_hash="ctx-abc", now_ms=1)


def test_no_credential_means_no_authorization_header():
    transport = FakeTransport([(200, _envelope())])
    HttpJsonInvoker(endpoint="https://x/y", transport=transport)(LEASE, CONTEXT)
    assert "Authorization" not in transport.calls[0]["headers"]


# --- HermesRunInvoker -----------------------------------------------------

def test_hermes_invoker_posts_the_run_shape_the_bridge_uses():
    transport = FakeTransport([(200, {"output_text": json.dumps({
        "verdict": "FLAG", "reason_codes": ["EVENT_PROXIMITY"],
        "risk_multiplier": "1", "confidence": "0.4",
        "narrative": "a tier-1 release falls inside the horizon", "horizon_ms": 60_000,
    })})])
    invoker = HermesRunInvoker(
        base_url="https://hermes.internal", transport=transport, credential="bearer1")
    raw = invoker(LEASE, CONTEXT)

    sent = transport.calls[0]
    assert sent["url"] == "https://hermes.internal/p/van/v1/runs"
    assert sent["headers"]["X-Hermes-Profile"] == "van"
    assert sent["headers"]["Authorization"] == "Bearer bearer1"
    assert set(sent["body"]) == {"profile", "input", "metadata"}
    assert sent["body"]["metadata"]["authority"] == "EVIDENCE_ONLY_NEVER_AN_ORDER"

    assessment = normalise(raw, model_id="fable-5.1", role=ModelRole.PRIMARY,
                           context_hash="ctx-abc", now_ms=5)
    assert assessment.verdict is Verdict.FLAG


def test_the_hermes_prompt_asks_for_only_the_assessment_json():
    invoker = HermesRunInvoker(base_url="https://h", transport=FakeTransport([]))
    prompt = invoker.prompt_for(CONTEXT)
    assert "EXACTLY ONE JSON object" in prompt
    assert "no markdown fence" in prompt
    # Every verdict and the order-field refusal must be stated, or a model will
    # be refused for following a contract it was never told.
    for verdict in ("CONCUR", "REDUCE", "ABSTAIN", "FLAG", "PROPOSE_RESEARCH",
                    "INSUFFICIENT_CONTEXT"):
        assert verdict in prompt
    assert "approved_size" in prompt
    # Jev can only participate as subordinate evidence inside this active Hermes
    # cognition run; the prompt must preserve the VATI authority boundary.
    assert "Optional Jev System-1 support" in prompt
    assert "jev_registered_batch" in prompt
    assert "authority_effect=NONE" in prompt or "subordinate evidence only" in prompt
    assert "never an independent/background trading loop" in prompt


@pytest.mark.parametrize("text", [
    "Sure! Here is my assessment: {\"verdict\": \"CONCUR\"}",
    "```json\n{\"verdict\": \"CONCUR\"}\n```",
    "{\"verdict\": \"CONCUR\"} and one more thought",
    "I cannot help with that.",
    "[{\"verdict\": \"CONCUR\"}]",
])
def test_hermes_output_that_is_not_only_json_is_refused(text):
    """Hermes is evidence, never authority. Anything but the object is refused."""
    invoker = HermesRunInvoker(
        base_url="https://h", transport=FakeTransport([(200, {"output_text": text})]))
    with pytest.raises(InvokerRefused) as exc:
        invoker(LEASE, CONTEXT)
    assert exc.value.code == "NOT_ONLY_JSON"


def test_a_run_response_with_no_text_is_refused():
    invoker = HermesRunInvoker(
        base_url="https://h", transport=FakeTransport([(200, {"run_id": "r1"})]))
    with pytest.raises(InvokerRefused) as exc:
        invoker(LEASE, CONTEXT)
    assert exc.value.code == "NO_RUN_OUTPUT"


def test_hermes_http_failure_is_refused():
    invoker = HermesRunInvoker(
        base_url="https://h", transport=FakeTransport([(401, {"error": "nope"})]))
    with pytest.raises(InvokerRefused) as exc:
        invoker(LEASE, CONTEXT)
    assert exc.value.code == "HTTP_STATUS"


# --- build_invoker --------------------------------------------------------

def test_build_invoker_selects_by_mode(monkeypatch):
    monkeypatch.setenv("VAN_TEST_TOKEN", "abc")
    http = build_invoker(
        CognitionConfig(invoker="http_json", endpoint="https://x",
                        credential_ref="env://VAN_TEST_TOKEN"),
        transport=FakeTransport([]))
    hermes = build_invoker(
        CognitionConfig(invoker="hermes_run", endpoint="https://h"),
        transport=FakeTransport([]))
    assert isinstance(http, HttpJsonInvoker) and http.credential == "abc"
    assert isinstance(hermes, HermesRunInvoker) and hermes.credential == ""


def test_build_invoker_fails_closed_on_an_unresolvable_credential():
    with pytest.raises(CognitionConfigError):
        build_invoker(CognitionConfig(
            invoker="http_json", endpoint="https://x",
            credential_ref="env://VAN_DEFINITELY_NOT_SET_12345"))


# --- the runtime join (the actual gap) ------------------------------------

def _wake(tmp_path, invoker, *, invoker_mode="none"):
    ledger = Ledger(tmp_path / "vati.sqlite")
    runtime = ShadowCognitionRuntime(
        ledger=ledger, invoker=invoker, invoker_mode=invoker_mode)
    mandate = TradingMandate.from_mapping(mandate_dict())
    authority = RiskAuthority(mandate)
    from conftest import eurusd as _eurusd  # fixture function, called directly
    contract = _eurusd.__wrapped__()
    ti = intent()
    snap = snapshot(contract)
    decision = authority.evaluate_safe(ti, snap)
    result = runtime.wake(intent=ti, decision=decision, snapshot=snap, now_ms=9_000)
    return ledger, runtime, decision, result


def test_with_no_invoker_the_abstention_is_explicit(tmp_path):
    ledger, runtime, decision, result = _wake(tmp_path, None)
    assert result.model_available is False
    assert result.assessment.verdict is Verdict.INSUFFICIENT_CONTEXT
    assert result.assessment.reason_codes == ("MODEL_UNAVAILABLE",)
    assert result.provider_attempts == 0
    assert runtime.invoker_mode == "none"
    # The deterministic decision is the one the caller already had.
    assert decision.decision.value in ("APPROVED", "REDUCED")


def test_with_a_configured_invoker_wake_records_a_real_assessment(tmp_path):
    transport = FakeTransport([(200, _envelope(
        verdict="REDUCE", reason_codes=["VOLATILITY_ELEVATED"],
        risk_multiplier="0.5"))])
    invoker = HttpJsonInvoker(endpoint="https://x/y", transport=transport)
    ledger, runtime, decision, result = _wake(
        tmp_path, invoker, invoker_mode="http_json")

    assert result.model_available is True
    assert result.assessment.verdict is Verdict.REDUCE
    assert result.assessment.risk_multiplier == Decimal("0.5")
    assert result.provider_attempts == 1
    assert runtime.invoker_mode == "http_json"
    # ...and the deterministic decision is unchanged either way (the whole
    # point of shadow cognition).
    assert decision.decision.value in ("APPROVED", "REDUCED")
    kinds = [e.kind for e in ledger.iter()]
    assert EventKind.COGNITIVE_CONTEXT in kinds
    assert EventKind.SHADOW_DECISION in kinds


def test_a_refused_result_falls_through_the_hierarchy_and_abstains(tmp_path):
    """Four rungs, every one answering something the contract refuses."""
    transport = FakeTransport([
        (200, _envelope(approved_size="9")),          # order fields
        (200, _envelope(verdict="GO_LIVE")),          # not in the vocabulary
        (200, _envelope(risk_multiplier="2")),        # above one
        (500, {"error": "down"}),                     # transport
    ])
    invoker = HttpJsonInvoker(endpoint="https://x/y", transport=transport)
    _ledger, _runtime, decision, result = _wake(
        tmp_path, invoker, invoker_mode="http_json")
    assert result.model_available is False
    assert result.assessment.reason_codes == ("MODEL_UNAVAILABLE",)
    assert result.provider_attempts == 4
    assert decision.decision.value in ("APPROVED", "REDUCED")


# --- bounded research (GAP-F-003 item 6) ----------------------------------
#
# The director, the agent factory and the mission ledger were reachable only
# from tests: a PROPOSE_RESEARCH verdict opened a mission that nobody ran. The
# runtime now runs it — but only under an explicit budget and only through a
# configured research invoker, because a packet nobody actually produced is a
# fabricated finding in an evidence ledger.

RESEARCH_BODY = {
    "claims": ["EUR liquidity operations were reviewed twice in 2019"],
    "source_ids": ["ecb-press-2019-03"],
    "retrieval_timestamps_ms": [9_000],
    "evidence_refs": ["artifact:ecb-press-2019-03"],
    "methods": ["primary-source-retrieval"],
    "counterevidence": ["the 2019 review did not precede a rate move"],
    "limitations": ["one source only"],
    "confidence": "MODERATE",
}


def _research_envelope(body=None):
    from vati.cognition.invokers import RESEARCH_CONTRACT_VERSION

    return {"contract_version": RESEARCH_CONTRACT_VERSION,
            "packet": dict(body or RESEARCH_BODY)}


def _wake_research(tmp_path, *, research_invoker, budget_micros,
                   verdict="PROPOSE_RESEARCH"):
    transport = FakeTransport([(200, _envelope(
        verdict=verdict, reason_codes=["EVIDENCE_THIN"],
        risk_multiplier="1"))])
    ledger = Ledger(tmp_path / "vati.sqlite")
    runtime = ShadowCognitionRuntime(
        ledger=ledger,
        invoker=HttpJsonInvoker(endpoint="https://x/y", transport=transport),
        invoker_mode="http_json",
        research_invoker=research_invoker,
        research_budget_micros=budget_micros,
    )
    mandate = TradingMandate.from_mapping(mandate_dict())
    authority = RiskAuthority(mandate)
    from conftest import eurusd as _eurusd

    contract = _eurusd.__wrapped__()
    ti = intent()
    snap = snapshot(contract)
    decision = authority.evaluate_safe(ti, snap)
    result = runtime.wake(intent=ti, decision=decision, snapshot=snap, now_ms=9_000)
    return ledger, runtime, decision, result


def test_build_research_invoker_needs_a_budget_and_a_destination():
    from vati.cognition.invokers import (
        HermesResearchInvoker, HttpJsonResearchInvoker, build_research_invoker,
    )

    # No invoker at all: nothing to commission research through.
    assert build_research_invoker(CognitionConfig()) is None
    # An invoker but no budget: research is never opened without one.
    assert build_research_invoker(CognitionConfig(
        invoker="http_json", endpoint="https://x")) is None
    # A budget but no research destination, for http_json: refused rather than
    # posted to the assessment endpoint, which answers a different question.
    assert build_research_invoker(CognitionConfig(
        invoker="http_json", endpoint="https://x",
        research_budget_micros=1_000)) is None
    built = build_research_invoker(CognitionConfig(
        invoker="http_json", endpoint="https://x",
        research_endpoint="https://x/research", research_budget_micros=1_000))
    assert isinstance(built, HttpJsonResearchInvoker)
    # Hermes runs are runs: the same base URL carries both, only the prompt
    # differs, so no second endpoint is required.
    hermes = build_research_invoker(CognitionConfig(
        invoker="hermes_run", endpoint="https://hermes",
        research_budget_micros=1_000))
    assert isinstance(hermes, HermesResearchInvoker)


def test_the_read_model_says_whether_research_is_actually_configured():
    """The read model states what this host can do, not what the build supports."""
    assert CognitionConfig().read_model()["research_configured"] is False
    # A budget with nowhere to send the request is not configured research.
    partial = CognitionConfig(invoker="http_json", endpoint="https://x",
                              research_budget_micros=1_000).read_model()
    assert partial["research_configured"] is False
    full = CognitionConfig(invoker="http_json", endpoint="https://x",
                           research_endpoint="https://x/r",
                           research_budget_micros=1_000).read_model()
    assert full["research_configured"] is True
    assert full["research_budget_micros"] == 1_000


def test_without_a_research_invoker_no_packet_is_recorded(tmp_path):
    """An empty result is an honest "no research happened"; a synthesised
    packet would be a fabricated finding (INV-EVID-001)."""
    _ledger, _runtime, decision, result = _wake_research(
        tmp_path, research_invoker=None, budget_micros=0)
    assert result.assessment.verdict is Verdict.PROPOSE_RESEARCH
    assert result.research_mission_id, "the mission was not opened"
    assert result.research_packets == ()
    assert decision.decision.value in ("APPROVED", "REDUCED")


def test_a_configured_research_invoker_produces_sealed_packets(tmp_path):
    from vati.cognition.invokers import HttpJsonResearchInvoker

    transport = FakeTransport([(200, _research_envelope())] * 4)
    _ledger, runtime, decision, result = _wake_research(
        tmp_path,
        research_invoker=HttpJsonResearchInvoker(
            endpoint="https://x/research", transport=transport),
        budget_micros=5_000_000)

    assert result.research_packets, "the mission was opened and never run"
    packet = result.research_packets[0]
    assert packet.claims and packet.source_ids and packet.methods
    assert packet.evidence_refs and packet.retrieved_ms
    assert packet.counterevidence, "a packet with no counterevidence is advocacy"
    # The request actually went out, carrying the mission and the role.
    sent = transport.calls[0]["body"]
    assert sent["mission"]["mission_id"] == result.research_mission_id
    assert sent["mission"]["authority"] == "EVIDENCE_ONLY_NEVER_AN_ORDER"
    assert sent["mission"]["role"] in runtime.research_roles
    # And none of it touched the deterministic decision.
    assert decision.decision.value in ("APPROVED", "REDUCED")


def test_a_research_result_without_provenance_is_refused(tmp_path):
    """No sources, no methods, no packet — the factory refuses rather than
    salvaging a free-form conclusion into the evidence ledger."""
    from vati.cognition.invokers import HttpJsonResearchInvoker

    bare = {"claims": ["it will go up"], "source_ids": [], "evidence_refs": [],
            "methods": []}
    transport = FakeTransport([(200, _research_envelope(bare))] * 8)
    _ledger, _runtime, _decision, result = _wake_research(
        tmp_path,
        research_invoker=HttpJsonResearchInvoker(
            endpoint="https://x/research", transport=transport),
        budget_micros=5_000_000)
    assert result.research_packets
    for packet in result.research_packets:
        assert packet.claims == ()
        assert "research_result_missing_required_evidence" in packet.failure_reason


def test_the_hermes_research_prompt_forbids_prose_and_names_the_contract():
    from vati.cognition.invokers import HermesResearchInvoker
    from vati.research.agents import ResearchAgentSpec
    from vati.research.director import FableResearchDirector, ResearchTrigger
    from vati.research.missions import MissionLedger

    director = FableResearchDirector(MissionLedger())
    mission = director.open(ResearchTrigger(
        trigger_id="t-1", question="what moved EUR liquidity in 2019?",
        evidence_ids=("seal-1",), data_domains=("external_web",),
        specialist_roles=("evidence",)), now_ms=1_000)
    transport = FakeTransport([(200, {"output_text": json.dumps(RESEARCH_BODY)})])
    invoker = HermesResearchInvoker(base_url="https://hermes", transport=transport)
    body = invoker(LEASE, mission, ResearchAgentSpec("evidence"))
    assert body["claims"] == RESEARCH_BODY["claims"]

    sent = transport.calls[0]
    assert sent["url"] == "https://hermes/p/van/v1/runs"
    prompt = sent["body"]["input"]
    assert "EXACTLY ONE JSON object" in prompt
    assert "never a decision" in prompt
    assert mission.hypothesis in prompt
    assert sent["body"]["metadata"]["authority"] == "EVIDENCE_ONLY_NEVER_AN_ORDER"


@pytest.mark.parametrize("text", ["not json", "```json\n{}\n```", "{} {}"])
def test_hermes_research_output_that_is_not_only_json_is_refused(text):
    from vati.cognition.invokers import HermesResearchInvoker
    from vati.research.agents import ResearchAgentSpec
    from vati.research.director import FableResearchDirector, ResearchTrigger
    from vati.research.missions import MissionLedger

    mission = FableResearchDirector(MissionLedger()).open(ResearchTrigger(
        trigger_id="t-1", question="q", evidence_ids=("s",),
        data_domains=("external_web",), specialist_roles=("evidence",)),
        now_ms=1_000)
    invoker = HermesResearchInvoker(
        base_url="https://hermes",
        transport=FakeTransport([(200, {"output_text": text})]))
    with pytest.raises(InvokerRefused):
        invoker(LEASE, mission, ResearchAgentSpec("evidence"))


def test_the_research_envelope_is_checked_before_the_body_is_read():
    from vati.cognition.invokers import HttpJsonResearchInvoker
    from vati.research.agents import ResearchAgentSpec
    from vati.research.director import FableResearchDirector, ResearchTrigger
    from vati.research.missions import MissionLedger

    mission = FableResearchDirector(MissionLedger()).open(ResearchTrigger(
        trigger_id="t-1", question="q", evidence_ids=("s",),
        data_domains=("external_web",), specialist_roles=("evidence",)),
        now_ms=1_000)
    spec = ResearchAgentSpec("evidence")
    for status, payload, code in (
        (500, {"error": "down"}, "HTTP_STATUS"),
        (200, {"contract_version": "something-else", "packet": {}}, "CONTRACT_VERSION"),
        (200, {"contract_version": "research-packet/5.1.0"}, "ENVELOPE_MALFORMED"),
        (200, b"<html>", "RESPONSE_MALFORMED"),
    ):
        invoker = HttpJsonResearchInvoker(
            endpoint="https://x/research",
            transport=FakeTransport([(status, payload)]))
        with pytest.raises(InvokerRefused) as exc:
            invoker(LEASE, mission, spec)
        assert exc.value.code == code
