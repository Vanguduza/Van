"""P0-VERIFY-001: verification must be performed, not asserted.

The audit's probe took a mission it controlled, wrote both halves of the proof — the
success contract that said what counted, and the receipt that said it had happened — and
reached VERIFIED_SUCCESS on `verifier_version: "i-say-so/1.0"` with
`evidence_refs: ["evidence://trust-me"]`. Nothing on the server observed anything.

The machinery to prevent it existed and was complete. `VerifierRegistry` and its adapters
were written, tested, and constructed only in tests; `create_app` never built one. That is
the isolation defect in its purest form: correct code with no production caller, and a
gate that therefore checked the shape of a receipt rather than its provenance.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from van_gateway.config import get_settings
from van_gateway.mission.models import (
    MissionOrigin,
    MissionState,
    SuccessContract,
    VerificationRecord,
    VerificationStatus,
)
from van_gateway.action.models import VerifierType
from van_gateway.automation.verifier import PostconditionSpec, VerificationOutcome
from van_gateway.verification.production import (
    UNOBSERVABLE_POSTCONDITION_KINDS,
    WIRED_MISSION_STRATEGIES,
    WIRED_POSTCONDITION_KINDS,
    build_automation_verifier,
    build_mission_registry,
)
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.mission.verifiers import EngineReportVerifier, VerifierRegistry
from van_gateway.models import OriginChannel
from van_gateway.storage.db import Store

CHECKABLE = SuccessContract(
    postconditions={"trade_intent_id": "ti-1", "trade_found": True},
    verifier_class="ledger-event",
)


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "verify.sqlite3"))
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "verify.sqlite3"))
    await s.migrate()
    return s


class FakeTrading:
    """A ledger that answers honestly about one trade and knows nothing of any other."""

    def __init__(self, known: dict | None = None) -> None:
        self.known = known or {}
        self.asked: list[str] = []

    def trade_detail(self, trade_intent_id: str):
        self.asked.append(trade_intent_id)
        return self.known.get(trade_intent_id)


async def _mission(svc, contract=CHECKABLE):
    m = await svc.create(
        owner_principal_id="owner",
        origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,
        title="place the order",
        goal="place the order",
        success_contract=contract,
    )
    for target in (MissionState.UNDERSTOOD, MissionState.PLANNED, MissionState.AUTHORIZED,
                   MissionState.RUNNING, MissionState.VERIFYING):
        m = await svc.transition(m.mission_id, target=target)
    return m


@pytest.mark.asyncio
class TestTheAuditProbe:
    async def test_there_is_no_parameter_to_hand_a_receipt_in(self, store):
        """The probe's exact move, which now cannot be expressed."""
        svc = MissionService(store)
        mission = await _mission(svc)
        forged = VerificationRecord(
            status=VerificationStatus.VERIFIED,
            observed_postconditions={"trade_found": True},
            evidence_refs=["evidence://trust-me"],
            verifier_version="i-say-so/1.0",
            verified_at_ms=1,
        )
        with pytest.raises(TypeError):
            await svc.transition(
                mission.mission_id,
                target=MissionState.VERIFIED_SUCCESS,
                verification=forged,
            )

    async def test_the_probes_contract_no_longer_reaches_success(self, store):
        """Writing a checkable contract is no longer enough to satisfy it."""
        svc = MissionService(store, verifiers=VerifierRegistry())
        mission = await _mission(svc)
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        assert (await svc.get(mission.mission_id)).state is MissionState.VERIFYING


@pytest.mark.asyncio
class TestTheRegistryIsTheOnlySource:
    async def test_the_stored_receipt_comes_from_the_adapter(self, store):
        trading = FakeTrading({"ti-1": {"status": "FILLED", "filled_qty": "1", "fill_price": "2"}})
        svc = MissionService(
            store, verifiers=build_mission_registry(store=store, trading=trading)
        )
        mission = await _mission(svc)
        await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)

        stored = await svc.verification_record(mission.mission_id)
        assert stored.verifier_version == "ledger-event/1"
        assert stored.evidence_refs == ["ledger://trade/ti-1"]
        assert trading.asked == ["ti-1"], "the ledger was never actually read"

    async def test_a_trade_the_ledger_does_not_know_is_not_a_success(self, store):
        """The executor may say it placed the order. The ledger is the authority."""
        trading = FakeTrading({})
        svc = MissionService(
            store, verifiers=build_mission_registry(store=store, trading=trading)
        )
        mission = await _mission(svc)
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)

    async def test_an_unreachable_ledger_is_not_a_pass(self, store):
        class Broken:
            def trade_detail(self, _):
                raise ConnectionError("ledger unavailable")

        svc = MissionService(
            store, verifiers=build_mission_registry(store=store, trading=Broken())
        )
        mission = await _mission(svc)
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)

    async def test_a_contract_that_names_no_trade_cannot_be_verified_by_the_ledger(self, store):
        """'Check the ledger' with nothing to look up must not resolve to 'nothing wrong'."""
        trading = FakeTrading({"ti-1": {"status": "FILLED"}})
        svc = MissionService(
            store, verifiers=build_mission_registry(store=store, trading=trading)
        )
        mission = await _mission(
            svc,
            SuccessContract(postconditions={"trade_found": True}, verifier_class="ledger-event"),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        assert trading.asked == [], "it should not have reached the ledger at all"


@pytest.mark.asyncio
class TestUnwiredCapabilitiesFailHonestly:
    async def test_an_unknown_strategy_gets_the_engine_report_fallback(self, store):
        trading = FakeTrading()
        registry = build_mission_registry(store=store, trading=trading)
        assert isinstance(registry.get("something-nobody-wired"), EngineReportVerifier)

    async def test_an_unwired_capability_can_still_reach_unverifiable(self, store):
        """The honest terminal has to remain reachable or the mission just hangs."""
        trading = FakeTrading()
        svc = MissionService(
            store, verifiers=build_mission_registry(store=store, trading=trading)
        )
        mission = await _mission(
            svc,
            SuccessContract(postconditions={"done": True}, verifier_class="api-readback"),
        )
        with pytest.raises(MissionError, match="VERIFICATION_INSUFFICIENT"):
            await svc.transition(mission.mission_id, target=MissionState.VERIFIED_SUCCESS)
        done = await svc.transition(mission.mission_id, target=MissionState.UNVERIFIABLE)
        assert done.state is MissionState.UNVERIFIABLE
        assert (await svc.verification_record(mission.mission_id)).verifier_version == (
            "engine-report/1"
        )

    async def test_the_wired_strategy_list_matches_what_the_registry_actually_holds(self, store):
        """A list that drifts from the registry would misdescribe what can be verified."""
        registry = build_mission_registry(store=store, trading=FakeTrading())
        for strategy in WIRED_MISSION_STRATEGIES:
            assert not isinstance(registry.get(strategy), EngineReportVerifier), strategy


@pytest.mark.asyncio
class TestTheProductionAppBuildsOne:
    async def test_create_app_installs_a_registry_with_the_wired_adapters(self, monkeypatch):
        """The finding's core fact: VerifierRegistry was constructed only in tests."""
        monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
        monkeypatch.setenv("VAN_INGRESS_TOKEN", "verify-ingress-token-0123456789")
        monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "verify-internal-token")
        # P0-SEC-001 — device enrolment is its own credential now.
        monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "verify-internal-token")
        get_settings.cache_clear()
        from van_gateway.app import create_app

        app = create_app()
        registry = app.state.missions.verifiers
        assert registry is not None
        for strategy in WIRED_MISSION_STRATEGIES:
            assert not isinstance(registry.get(strategy), EngineReportVerifier), strategy


@pytest.mark.asyncio
class TestAutomationVerificationIsWired:
    """P1-AUTO-001: the observer map was empty in production.

    Every automation run therefore returned UNVERIFIABLE and `owner_success` could never
    be true. The tests passed because they injected their own observers — the defect lived
    exactly in the gap between what the tests built and what create_app built.
    """

    async def test_create_app_installs_a_non_empty_observer_map(self, monkeypatch):
        monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
        monkeypatch.setenv("VAN_INGRESS_TOKEN", "verify-ingress-token-0123456789")
        monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "verify-internal-token")
        # P0-SEC-001 — device enrolment is its own credential now.
        monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "verify-internal-token")
        get_settings.cache_clear()
        from van_gateway.app import create_app

        app = create_app()
        observers = app.state.automation_dispatcher.verifier.observers
        assert observers, "the production observer map is empty"
        assert set(observers) == set(WIRED_POSTCONDITION_KINDS)

    async def test_a_read_back_confirms_from_the_provider_not_from_the_engine(self, store):
        class FakeGoogle:
            def __init__(self):
                self.queries = []

            async def drive_search(self, query):
                self.queries.append(query)
                return [{"id": "file-1"}]

        google = FakeGoogle()
        verifier = build_automation_verifier(store=store, google=google)
        result = await verifier.verify(
            spec=PostconditionSpec(kind="READ_BACK", field="exists", expected=True),
            verifier_type=VerifierType.READ_BACK,
            engine_reported_success=False,  # the engine says it failed; the world disagrees
            context={"readback": {"surface": "drive", "query": "Q3 report"}},
        )
        assert result.outcome is VerificationOutcome.VERIFIED
        assert google.queries == ["Q3 report"], "the provider was never asked"

    async def test_an_engine_success_with_nothing_at_the_provider_is_a_failure(self, store):
        class EmptyGoogle:
            async def drive_search(self, query):
                return []

        verifier = build_automation_verifier(store=store, google=EmptyGoogle())
        result = await verifier.verify(
            spec=PostconditionSpec(kind="READ_BACK", field="exists", expected=True),
            verifier_type=VerifierType.READ_BACK,
            engine_reported_success=True,
            context={"readback": {"surface": "drive", "query": "Q3 report"}},
        )
        assert result.outcome is VerificationOutcome.FAILED
        assert "despite engine success" in (result.detail or "")

    async def test_an_unreachable_provider_is_unverifiable_not_verified(self, store):
        class BrokenGoogle:
            async def drive_search(self, query):
                raise ConnectionError("provider down")

        verifier = build_automation_verifier(store=store, google=BrokenGoogle())
        result = await verifier.verify(
            spec=PostconditionSpec(kind="READ_BACK"),
            verifier_type=VerifierType.READ_BACK,
            engine_reported_success=True,
            context={"readback": {"surface": "drive", "query": "x"}},
        )
        assert result.outcome is VerificationOutcome.UNVERIFIABLE

    async def test_a_surface_with_no_independent_readback_is_refused(self, store):
        verifier = build_automation_verifier(store=store, google=object())
        result = await verifier.verify(
            spec=PostconditionSpec(kind="READ_BACK"),
            verifier_type=VerifierType.READ_BACK,
            engine_reported_success=True,
            context={"readback": {"surface": "slack", "query": "x"}},
        )
        assert result.outcome is VerificationOutcome.UNVERIFIABLE

    @pytest.mark.parametrize("kind", sorted(UNOBSERVABLE_POSTCONDITION_KINDS))
    async def test_a_kind_with_no_independent_source_stays_unverifiable(self, store, kind):
        """Named and reasoned about, rather than quietly answered with something optimistic."""
        verifier = build_automation_verifier(store=store, google=object())
        result = await verifier.verify(
            spec=PostconditionSpec(kind=kind),
            verifier_type=VerifierType.RECEIPT,
            engine_reported_success=True,
            context={},
        )
        assert result.outcome is VerificationOutcome.UNVERIFIABLE
        assert UNOBSERVABLE_POSTCONDITION_KINDS[kind]

    async def test_both_systems_are_built_from_the_same_observations(self):
        """P2-COH-002, verifier half: one place answers 'what can VAN observe?'."""
        from van_gateway.verification import observations, production
        import inspect

        source = inspect.getsource(production)
        assert "from van_gateway.verification import observations" in source
        for name in ("trading_ledger_readback", "browser_evidence_readback",
                     "google_resource_readback", "automation_run_state_predicate"):
            assert hasattr(observations, name)
            assert f"observations.{name}" in source, (
                f"{name} is defined in the shared module but production does not use it"
            )
