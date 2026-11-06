"""One episode is one vote, and only the owner's episodes are votes.

M4 — a mission and the command that opened it were two votes. Reviewer D's probe:
`mission:M` (opened by `cmd-1`) + `command:cmd-1` + one other mission came out EVIDENCED,
may_act_on True, from two real episodes.

O2 — `_require_episode` never read `missions.owner_principal_id`, so three missions owned by
"mallory" made the owner's assertion EVIDENCED.
"""

from __future__ import annotations

import pytest
from conftest_automation import make_store

from van_gateway.understanding.owner_model import (
    AssertionState,
    ObservationOrigin,
    OwnerCognitiveModel,
    OwnerModelError,
    OwnerModelField,
)

SYS = ObservationOrigin.SYSTEM_OBSERVED
FIELD = OwnerModelField.COMMUNICATION_PREFERENCE


async def _mission(store, owner: str, title: str, source_command_id: str | None = None) -> str:
    from van_gateway.mission.models import AuthorityEnvelope, MissionOrigin
    from van_gateway.mission.service import MissionService
    from van_gateway.models import OriginChannel

    kw = {}
    if source_command_id:
        kw["authority_envelope"] = AuthorityEnvelope(source_command_id=source_command_id)
    m = await MissionService(store).create(
        owner_principal_id=owner, origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE, title=title, goal=title, **kw)
    return m.mission_id


async def _command(store, command_id: str, device_id: str | None = None) -> None:
    await store.execute(
        "INSERT INTO audit(id, command_id, device_id, result, created_at_unix) "
        "VALUES (?, ?, ?, 'ok', 1)", (f"aud-{command_id}", command_id, device_id))


async def _bind(store, device_id: str, owner: str) -> None:
    await store.execute(
        "INSERT INTO owner_device_bindings(binding_id, owner_principal_id, device_id, "
        "device_key_fingerprint, public_key_pem, key_security_level, app_package_name, "
        "app_signing_cert_sha256, status, bound_at_ms) "
        "VALUES (?, ?, ?, ?, 'pem', 'STRONGBOX', 'app', 'cert', 'ACTIVE', 1)",
        (f"bind-{device_id}", owner, device_id, f"fp-{device_id}"))


async def _observe(model, ref, owner="owner"):
    return await model.observe(owner_principal_id=owner, field=FIELD, value="terse",
                               episode_ref=ref, origin=SYS)


# ------------------------------------------------------------------ M4


async def test_a_mission_and_its_source_command_are_one_vote(tmp_path):
    """D's probe O1, asserted: two real episodes cannot make EVIDENCED."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    await _command(store, "cmd-1")
    opened = await _mission(store, "owner", "one", source_command_id="cmd-1")
    other = await _mission(store, "owner", "two")
    for ref in (f"mission:{opened}", "command:cmd-1", f"mission:{other}"):
        a = await _observe(model, ref)
    assert a.evidencing_episode_count == 2
    assert a.state is AssertionState.CANDIDATE and not a.may_act_on
    assert a.confidence == pytest.approx(0.45)
    # Both refs stay on record for provenance; only the vote is shared.
    assert a.supporting_episode_refs == sorted(
        ["command:cmd-1", f"mission:{opened}", f"mission:{other}"])

    # A genuinely third episode is what promotes it.
    third = await _mission(store, "owner", "three")
    a = await _observe(model, f"mission:{third}")
    assert a.evidencing_episode_count == 3 and a.state is AssertionState.EVIDENCED


async def test_command_observed_before_its_mission_existed_is_still_one_vote(tmp_path):
    """Keying by the source command makes the order irrelevant: the command's ref was
    recorded while no mission named it, and the mission opened later joins its vote."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    await _command(store, "cmd-early")
    other = await _mission(store, "owner", "two")
    await _observe(model, "command:cmd-early")
    late = await _mission(store, "owner", "late", source_command_id="cmd-early")
    await _observe(model, f"mission:{other}")
    a = await _observe(model, f"mission:{late}")
    assert a.evidencing_episode_count == 2
    assert a.state is AssertionState.CANDIDATE and not a.may_act_on


# ------------------------------------------------------------------ O2


async def test_another_principals_missions_are_not_the_owners_votes(tmp_path):
    """D's probe O2, asserted."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    for i in range(3):
        mid = await _mission(store, "mallory", f"m{i}")
        with pytest.raises(OwnerModelError) as err:
            await _observe(model, f"mission:{mid}")
        assert err.value.code == "OWNER_MODEL_EPISODE_FOREIGN_PRINCIPAL"
    assert await model.actionable("owner") == []
    assert await store.fetchone("SELECT 1 FROM owner_cognitive_model") is None


async def test_device_principal_resolves_through_the_owner_device_binding(tmp_path):
    """Command-opened missions are owned by `device:<id>` (command/mission_link.py). They
    are the owner's exactly when that device is bound to the owner."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    await _bind(store, "dev-owner", "owner")
    await _bind(store, "dev-mallory", "mallory")
    mine = await _mission(store, "device:dev-owner", "mine")
    a = await _observe(model, f"mission:{mine}")
    assert a.evidencing_episode_count == 1
    theirs = await _mission(store, "device:dev-mallory", "theirs")
    unbound = await _mission(store, "device:dev-nobody", "unbound")
    for ref in (f"mission:{theirs}", f"mission:{unbound}"):
        with pytest.raises(OwnerModelError) as err:
            await _observe(model, ref)
        assert err.value.code == "OWNER_MODEL_EPISODE_FOREIGN_PRINCIPAL"


async def test_a_command_attributed_to_another_principal_is_refused(tmp_path):
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    await _bind(store, "dev-mallory", "mallory")
    # Attributed through the mission it opened.
    await _command(store, "cmd-m")
    await _mission(store, "mallory", "m", source_command_id="cmd-m")
    # Attributed through its device's binding.
    await _command(store, "cmd-d", device_id="dev-mallory")
    for ref in ("command:cmd-m", "command:cmd-d"):
        with pytest.raises(OwnerModelError) as err:
            await _observe(model, ref)
        assert err.value.code == "OWNER_MODEL_EPISODE_FOREIGN_PRINCIPAL"
    # The audit table has no principal column: a command nothing attributes is accepted,
    # unchanged from before (the one case this check cannot decide).
    await _command(store, "cmd-bare")
    assert (await _observe(model, "command:cmd-bare")).evidencing_episode_count == 1
