"""Rev 1 §§6, 34, 36, 38-39 — permissions, computer use, verifiers.

Three boundaries, one theme: an authority nobody can see, an operation nobody
typed, and a success nobody observed are the same failure in three costumes.
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.browser.models import BrowserBoundaryType
from van_gateway.capability.permissions import (
    KNOWN_PERMISSIONS,
    PermissionError_,
    PermissionOrigin,
    PermissionRegistry,
)
from van_gateway.computer_use.fabric import (
    ComputerInteractionFabric,
    ComputerUseError,
    OperationRequest,
    OperationState,
    OperationType,
    Surface,
)
from van_gateway.mission.models import SuccessContract, VerificationStatus
from van_gateway.mission.verifiers import (
    ApiReadbackVerifier,
    EngineReportVerifier,
    VerifierRegistry,
)
from van_gateway.models import ActionClass

NOW = 1_800_000_000_000
DAY = 24 * 60 * 60 * 1000


# ------------------------------------------------------------- §36 permissions


async def test_a_grant_without_a_stated_origin_is_refused(tmp_path):
    """A permission whose provenance nobody recorded is one VAN gave itself."""
    registry = PermissionRegistry(await make_store(tmp_path))
    with pytest.raises(PermissionError_, match="ORIGIN_REQUIRED"):
        await registry.grant(
            permission="email.send", origin=PermissionOrigin.OWNER_DECISION,
            origin_evidence_ref="",
        )


async def test_a_grant_carrying_credential_material_is_refused(tmp_path):
    """§36 — no raw provider tokens, no cookie export. A secret in a table the
    owner can read is a secret on the owner's phone."""
    registry = PermissionRegistry(await make_store(tmp_path))
    for poison in ("Bearer ya29.aVeryLongLookingAccessToken", "cookie: session=abc",
                   "ghp_0123456789abcdefghij"):
        with pytest.raises(PermissionError_, match="SECRET_MATERIAL"):
            await registry.grant(
                permission="email.read", origin=PermissionOrigin.OAUTH_CONSENT,
                origin_evidence_ref=poison,
            )


async def test_an_unlisted_permission_cannot_be_granted(tmp_path):
    """A permissions screen that says "other" is not a permissions screen."""
    registry = PermissionRegistry(await make_store(tmp_path))
    with pytest.raises(PermissionError_, match="UNKNOWN"):
        await registry.grant(
            permission="do.anything", origin=PermissionOrigin.OWNER_DECISION,
            origin_evidence_ref="decision://d1",
        )


async def test_the_owner_view_surfaces_stale_and_never_used_grants(tmp_path):
    """§36 — "last use" is what makes an accumulated permission visible."""
    registry = PermissionRegistry(await make_store(tmp_path))
    fresh = await registry.grant(
        permission="calendar.read", origin=PermissionOrigin.OAUTH_CONSENT,
        origin_evidence_ref="oauth://consent-1", now_ms=NOW,
    )
    stale = await registry.grant(
        permission="github.merge", origin=PermissionOrigin.OWNER_DECISION,
        origin_evidence_ref="decision://old", now_ms=NOW - 200 * DAY,
    )
    await registry.record_use(fresh.grant_id, now_ms=NOW)

    view = await registry.owner_view(now_ms=NOW)
    assert stale.grant_id in view["stale_grants"]
    assert fresh.grant_id not in view["stale_grants"]
    by_id = {g["grant_id"]: g for g in view["granted"]}
    assert by_id[fresh.grant_id]["use_count"] == 1
    assert by_id[stale.grant_id]["never_used"] is True
    assert set(view["available_permissions"]) == set(KNOWN_PERMISSIONS)


async def test_revoking_is_idempotent_and_visible(tmp_path):
    registry = PermissionRegistry(await make_store(tmp_path))
    grant = await registry.grant(
        permission="vati.execute", origin=PermissionOrigin.OWNER_DECISION,
        origin_evidence_ref="decision://d9", now_ms=NOW,
    )
    assert await registry.revoke(grant.grant_id, now_ms=NOW) is True
    assert await registry.revoke(grant.grant_id, now_ms=NOW) is False
    view = await registry.owner_view(now_ms=NOW)
    assert grant.grant_id in [g["grant_id"] for g in view["revoked"]]
    assert grant.grant_id not in [g["grant_id"] for g in view["granted"]]


# --------------------------------------------------------- §38 computer use


def test_there_is_no_do_anything_primitive():
    """§38 — typed operations only. This set is the boundary."""
    names = {op.value for op in OperationType}
    for forbidden in ("RUN_ARBITRARY", "EXECUTE", "EVAL", "SHELL", "SCRIPT"):
        assert forbidden not in names


def test_a_typed_operation_carries_its_own_ceiling():
    assert OperationType.READ.max_action_class is ActionClass.A2
    assert OperationType.CLICK.max_action_class is ActionClass.A3
    # No operation type may carry A4: that needs approval bound to the exact
    # action, which is not a standing property of a type.
    assert all(op.max_action_class is not ActionClass.A4 for op in OperationType)


async def test_the_generic_fabric_is_never_an_a4_surface(tmp_path):
    """§2.4 — the browser rule, generalised rather than relaxed."""
    fabric = ComputerInteractionFabric(await make_store(tmp_path))
    with pytest.raises(ComputerUseError, match="ACTION_CLASS_PROHIBITED"):
        await fabric.begin(OperationRequest(
            mission_id="m1", surface=Surface.DESKTOP, target_application="broker terminal",
            operation_type=OperationType.CLICK, action_class=ActionClass.A4,
            verifier_type="SCREENSHOT",
        ))


async def test_an_operation_cannot_exceed_its_type_ceiling(tmp_path):
    fabric = ComputerInteractionFabric(await make_store(tmp_path))
    with pytest.raises(ComputerUseError, match="ABOVE_TYPE_CEILING"):
        await fabric.begin(OperationRequest(
            mission_id="m1", surface=Surface.BROWSER, target_application="portal",
            operation_type=OperationType.READ, action_class=ActionClass.A3,
        ))


async def test_a_mutation_needs_a_verifier_up_front_and_evidence_at_the_end(tmp_path):
    """§34 — on every surface, not just the browser.

    P2-CU-001 — the fabric is given a DESKTOP worker here because this test is about the
    evidence rule, not about which surfaces are staffed. In production `SURFACE_WORKERS` is
    empty and `begin` refuses before any of this; `TestTheFabricRefusesWhatItCannotPerform`
    is where that is stated.
    """
    fabric = ComputerInteractionFabric(
        await make_store(tmp_path), workers=frozenset({Surface.DESKTOP}),
    )
    with pytest.raises(ComputerUseError, match="MUTATION_WITHOUT_VERIFIER"):
        await fabric.begin(OperationRequest(
            mission_id="m1", surface=Surface.DESKTOP, target_application="app",
            operation_type=OperationType.TYPE_TEXT, action_class=ActionClass.A3,
        ))

    operation_id = await fabric.begin(OperationRequest(
        mission_id="m1", surface=Surface.DESKTOP, target_application="app",
        operation_type=OperationType.TYPE_TEXT, action_class=ActionClass.A3,
        verifier_type="SCREENSHOT",
    ))
    with pytest.raises(ComputerUseError, match="COMPLETION_REQUIRES_EVIDENCE"):
        await fabric.complete(operation_id, state=OperationState.COMPLETED)
    await fabric.complete(
        operation_id, state=OperationState.COMPLETED, evidence_ref="shot://1"
    )
    ops = await fabric.for_mission("m1")
    assert ops[0]["state"] == "COMPLETED" and ops[0]["evidence_ref"] == "shot://1"


def test_boundary_classification_generalises_the_browser_rule():
    """§38 — a prompt the target surface can provoke is not supervision."""
    assert ComputerInteractionFabric.classify_boundary(
        payment_suspected=True
    ) is BrowserBoundaryType.POLICY_FORBIDDEN
    assert ComputerInteractionFabric.classify_boundary(
        injection_suspected=True
    ) is BrowserBoundaryType.POLICY_FORBIDDEN
    assert ComputerInteractionFabric.classify_boundary(
        requested_action_class=ActionClass.A4
    ) is BrowserBoundaryType.POLICY_FORBIDDEN
    assert ComputerInteractionFabric.classify_boundary(
        within_declared_scope=False
    ) is BrowserBoundaryType.OWNER_EXTENSION_REQUIRED


# ------------------------------------------------------------- §6 verifiers


async def test_an_engine_report_can_never_confirm(tmp_path):
    """§6 — "the worker returned OK" is representable, never sufficient."""
    contract = SuccessContract(postconditions={"exists": True}, verifier_class="x")
    record = await EngineReportVerifier().verify(
        contract, {"engine_reported_success": True, "now_ms": NOW}
    )
    assert record.status is VerificationStatus.UNVERIFIABLE
    assert record.supports_success is False


async def test_a_readback_that_satisfies_everything_confirms():
    async def observe(_context):
        return {
            "notebook_exists": True, "minimum_sources": 7,
            "evidence_refs": ["provider-readback://nb-1"],
        }

    contract = SuccessContract(
        postconditions={"notebook_exists": True, "minimum_sources": 5},
        verifier_class="api_readback",
    )
    record = await ApiReadbackVerifier(observe).verify(contract, {"now_ms": NOW})
    assert record.status is VerificationStatus.VERIFIED
    assert record.supports_success is True
    # A numeric postcondition is a floor: 7 satisfies "at least 5".
    assert record.observed_postconditions["minimum_sources"] == 7


async def test_a_postcondition_the_observation_did_not_mention_counts_as_missing():
    """Absence of contradiction is not confirmation."""
    async def observe(_context):
        return {"notebook_exists": True, "evidence_refs": ["provider-readback://nb-1"]}

    contract = SuccessContract(
        postconditions={"notebook_exists": True, "owner_account_verified": True},
        verifier_class="api_readback",
    )
    record = await ApiReadbackVerifier(observe).verify(contract, {"now_ms": NOW})
    assert record.status is VerificationStatus.FAILED
    assert record.missing_postconditions == ["owner_account_verified"]


async def test_satisfied_but_uncitable_still_cannot_confirm():
    """§55 — evidence is not optional for a success claim."""
    async def observe(_context):
        return {"exists": True}

    contract = SuccessContract(postconditions={"exists": True}, verifier_class="x")
    record = await ApiReadbackVerifier(observe).verify(contract, {"now_ms": NOW})
    assert record.status is VerificationStatus.UNVERIFIABLE
    assert record.supports_success is False


async def test_an_unreachable_target_is_unverifiable_not_a_pass():
    async def observe(_context):
        raise TimeoutError("provider down")

    contract = SuccessContract(postconditions={"exists": True}, verifier_class="x")
    record = await ApiReadbackVerifier(observe).verify(contract, {"now_ms": NOW})
    assert record.status is VerificationStatus.UNVERIFIABLE
    assert record.observed_postconditions["error"] == "TimeoutError"


async def test_an_unknown_strategy_falls_back_to_the_honest_verifier():
    """Never an optimistic default."""
    registry = VerifierRegistry()
    record = await registry.verify(
        strategy="something_nobody_registered",
        contract=SuccessContract(postconditions={"x": True}, verifier_class="y"),
        context={"now_ms": NOW},
    )
    assert record.status is VerificationStatus.UNVERIFIABLE


# --------------------------------------------------------------------- P2-CU-001

class TestTheFabricRefusesWhatItCannotPerform:
    """P2-CU-001 — the boundary is complete and no worker exists for any surface.

    The audit's disposition was "delete or fold", and the closure blueprint's owner
    decision 6 said delete on the description "a stub". Reading the module corrects that:
    the refusals are real, ordered and tested, and the ledger is durable. What was missing
    was an executor, and the defect was that nothing said so — `begin` recorded an
    operation nobody would perform and every matrix listing the fabric read it as built.

    These tests state the corrected disposition: the module stays, and the missing executor
    is a refusal at runtime rather than a claim in a document.
    """

    async def test_every_surface_is_refused_because_none_has_a_worker(self, tmp_path):
        from van_gateway.computer_use.fabric import SURFACE_WORKERS

        assert SURFACE_WORKERS == frozenset()
        fabric = ComputerInteractionFabric(await make_store(tmp_path))
        for surface in Surface:
            with pytest.raises(ComputerUseError) as exc:
                await fabric.begin(
                    OperationRequest(
                        mission_id="m-1", surface=surface, target_application="anything",
                        operation_type=OperationType.READ, action_class=ActionClass.A1,
                    )
                )
            assert str(exc.value).startswith("OPERATION_NO_WORKER_FOR_SURFACE"), surface

    async def test_a_refused_operation_leaves_no_row_claiming_it_is_pending(self, tmp_path):
        """A PENDING row for work nobody will do is the owner being told it is queued."""
        fabric = ComputerInteractionFabric(await make_store(tmp_path))
        with pytest.raises(ComputerUseError):
            await fabric.begin(
                OperationRequest(
                    mission_id="m-2", surface=Surface.DESKTOP, target_application="a thing",
                    operation_type=OperationType.READ, action_class=ActionClass.A1,
                )
            )
        assert await fabric.for_mission("m-2") == []

    async def test_a_prohibited_class_is_refused_as_prohibited_not_as_unconfigured(self, tmp_path):
        """The ordering that matters most.

        "No worker for DESKTOP" invites someone to start a worker. If an A4 request were
        reported that way, the absolute prohibition would read as one worker away from
        permitted — which is how a policy boundary becomes a configuration option.
        """
        fabric = ComputerInteractionFabric(await make_store(tmp_path))
        for action_class in (ActionClass.A4, ActionClass.A5):
            with pytest.raises(ComputerUseError) as exc:
                await fabric.begin(
                    OperationRequest(
                        mission_id="m-3", surface=Surface.DESKTOP,
                        target_application="a thing", operation_type=OperationType.CLICK,
                        action_class=action_class, verifier_type="SCREENSHOT",
                    )
                )
            assert str(exc.value).startswith("OPERATION_ACTION_CLASS_PROHIBITED"), action_class

    async def test_a_worker_makes_the_fabric_work_without_any_other_change(self, tmp_path):
        """The claim that this is a registration away from working, checked.

        P2-VERIFY-002 taught that an unconstructed class rots into a stub nobody notices.
        Registering a surface here must be the whole change — if it is not, the guard is
        hiding rot rather than reporting a gap.
        """
        fabric = ComputerInteractionFabric(
            await make_store(tmp_path), workers=frozenset({Surface.DESKTOP}),
        )
        operation_id = await fabric.begin(
            OperationRequest(
                mission_id="m-4", surface=Surface.DESKTOP, target_application="a thing",
                operation_type=OperationType.READ, action_class=ActionClass.A1,
            )
        )
        assert operation_id.startswith("cop_")
        rows = await fabric.for_mission("m-4")
        assert [r["state"] for r in rows] == ["PENDING"]
        # And a surface without a worker is still refused on the same fabric.
        with pytest.raises(ComputerUseError):
            await fabric.begin(
                OperationRequest(
                    mission_id="m-4", surface=Surface.TERMINAL, target_application="a thing",
                    operation_type=OperationType.READ, action_class=ActionClass.A1,
                )
            )

    async def test_the_surface_report_covers_every_surface(self, tmp_path):
        surfaces = ComputerInteractionFabric(await make_store(tmp_path)).surfaces()
        assert set(surfaces) == {s.value for s in Surface}
        assert not any(surfaces.values())
