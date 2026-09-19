"""P1-GOOG-002 and P4-CMD-001 — the owner sealed *which* thing, in their own words.

Two defects in the same path. The authority check required the sealed parameters to be a
subset of the submitted ones, so a parameter the resolver did not seal was unconstrained:
`google.notebook.note.create` is A3, requires `notebook_id`, and the resolver sealed only
`title` — so Hermes chose which of the owner's notebooks the note landed in, and the sealed
record said nothing about it. Separately, the resolver matched against casefolded text, so
the title it sealed was already lowercased.
"""

from __future__ import annotations

import time

import pytest

from conftest_automation import enroll_device, make_store
from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.command.authority import (
    CommandAuthorityError,
    CommandAuthorityRecord,
    CommandAuthorityService,
)
from van_gateway.command.resolver import TypedCommandResolver
from van_gateway.models import ActionClass, OriginChannel, PrincipalType

NOTE_ACTION = ActionDefinition(
    action_id="google.notebook.note.create",
    action_class=ActionClass.A3,
    mutates_state=True,
    allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.HERMES_AGENT},
    verifier_type=VerifierType.READ_BACK,
    parameter_schema={
        "required": ["notebook_id", "title"],
        "properties": {"notebook_id": "string", "title": "string", "body": "string"},
    },
)

READ_ACTION = ActionDefinition(
    action_id="owner.context.read",
    action_class=ActionClass.A1,
    mutates_state=False,
    allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.HERMES_AGENT},
    verifier_type=VerifierType.NONE,
    parameter_schema={"required": ["topic"], "properties": {"topic": "string"}},
)


async def _sealed(tmp_path, *, action_id, parameters, action_class=ActionClass.A3):
    store = await make_store(tmp_path)
    await enroll_device(store, "dev-1")
    authority = CommandAuthorityService(store)
    now = int(time.time())
    record = await authority.seal(CommandAuthorityRecord(
        command_id="cmd-1",
        device_id="dev-1",
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1",
        origin_channel=OriginChannel.UI,
        signed_action_class=action_class,
        effective_action_class=action_class,
        typed_action_id=action_id,
        typed_parameter_constraints=parameters,
        snapshot_id="snap-1",
        context_digest="digest",
        issued_at_unix=now,
        sealed_at_unix_ms=now * 1000,
    ))
    return authority, record


async def _verify(authority, action, submitted):
    return await authority.authorize_action(
        command_id="cmd-1",
        action=action,
        principal_type=PrincipalType.OWNER_DEVICE,
        requested_by="device:dev-1",
        snapshot_id="snap-1",
        turn_id=None,
        parameters=submitted,
    )


@pytest.mark.asyncio
async def test_a_notebook_the_owner_never_chose_is_refused(tmp_path):
    """The finding. `notebook_id` was outside the sealed set, so it was free."""
    authority, _record = await _sealed(
        tmp_path, action_id=NOTE_ACTION.action_id, parameters={"title": "Dial Health"}
    )
    with pytest.raises(CommandAuthorityError) as raised:
        await _verify(authority, NOTE_ACTION, {"title": "Dial Health", "notebook_id": "nb-hermes-picked"})
    assert str(raised.value) == "unsealed_required_parameter:notebook_id"


@pytest.mark.asyncio
async def test_a_sealed_notebook_is_honoured_and_cannot_be_swapped(tmp_path):
    authority, _record = await _sealed(
        tmp_path, action_id=NOTE_ACTION.action_id,
        parameters={"title": "Dial Health", "notebook_id": "nb-owner"},
    )
    record, _age = await _verify(
        authority, NOTE_ACTION, {"title": "Dial Health", "notebook_id": "nb-owner"}
    )
    assert record.typed_parameter_constraints["notebook_id"] == "nb-owner"

    with pytest.raises(CommandAuthorityError) as raised:
        await _verify(
            authority, NOTE_ACTION, {"title": "Dial Health", "notebook_id": "nb-somewhere-else"}
        )
    assert str(raised.value) == "typed_parameter_mismatch:notebook_id"


@pytest.mark.asyncio
async def test_an_extra_parameter_nobody_sealed_is_refused(tmp_path):
    """The rule that matters most. Sealing `notebook_id` alone would stop the notebook
    being swapped but not stop a `share_with` the owner never saw."""
    authority, _record = await _sealed(
        tmp_path, action_id=NOTE_ACTION.action_id,
        parameters={"title": "Dial Health", "notebook_id": "nb-owner"},
    )
    with pytest.raises(CommandAuthorityError) as raised:
        await _verify(authority, NOTE_ACTION, {
            "title": "Dial Health", "notebook_id": "nb-owner", "share_with": "someone@example.com",
        })
    assert str(raised.value) == "unsealed_parameter:share_with"


@pytest.mark.asyncio
async def test_a_read_may_still_carry_arguments_nobody_sealed(tmp_path):
    """A1 reads legitimately carry paging and filters. Refusing those would break every
    read path to fix a mutation problem."""
    authority, _record = await _sealed(
        tmp_path, action_id=READ_ACTION.action_id, parameters={"topic": "VAN"},
        action_class=ActionClass.A1,
    )
    record, _age = await _verify(authority, READ_ACTION, {"topic": "VAN", "limit": 20})
    assert record.typed_action_id == READ_ACTION.action_id


# ---------------------------------------------------------------- P4-CMD-001

def test_the_owner_s_capitalisation_survives_into_the_sealed_parameters():
    resolved = TypedCommandResolver().resolve("Create a new note in NotebookLM named Dial Health")
    assert resolved.parameters["title"] == "Dial Health"
    # The normalised text is still casefolded — that is what matching is done against —
    # but it is not where the parameters come from any more.
    assert resolved.normalized_text == "create a new note in notebooklm named dial health"


def test_matching_is_still_case_insensitive():
    for phrasing in (
        "create a new note in notebooklm named Dial Health",
        "CREATE A NEW NOTE IN NOTEBOOKLM NAMED Dial Health",
        "Create A New Note In NotebookLM Named Dial Health",
    ):
        resolved = TypedCommandResolver().resolve(phrasing)
        assert resolved.action_id == "google.notebook.note.create", phrasing
        assert resolved.parameters["title"] == "Dial Health", phrasing


def test_research_and_context_queries_keep_their_case_too():
    assert TypedCommandResolver().resolve(
        "Research Zimbabwe Stock Exchange listings"
    ).parameters["query"] == "Zimbabwe Stock Exchange listings"
    assert TypedCommandResolver().resolve(
        "What do you know about NotebookLM?"
    ).parameters["topic"] == "NotebookLM"


def test_the_owner_can_name_the_notebook(tmp_path):
    resolved = TypedCommandResolver().resolve(
        "Create a notebooklm note called Dial Health in notebook nb-42"
    )
    assert resolved.parameters == {"notebook_id": "nb-42", "title": "Dial Health"}


def test_a_configured_default_is_sealed_and_a_named_notebook_wins():
    resolver = TypedCommandResolver(default_notebook_id="nb-owner-default")
    default = resolver.resolve("Create a new note in NotebookLM named Dial Health")
    assert default.parameters["notebook_id"] == "nb-owner-default"

    named = resolver.resolve("Create a notebooklm note called Dial Health in notebook nb-42")
    assert named.parameters["notebook_id"] == "nb-42"


def test_with_no_default_the_destination_is_simply_absent():
    """And is therefore refused by the authority check, rather than chosen by the model.
    A refusal the owner can act on beats a note in a notebook they did not pick."""
    resolved = TypedCommandResolver().resolve("Create a new note in NotebookLM named Dial Health")
    assert "notebook_id" not in resolved.parameters
