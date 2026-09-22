from __future__ import annotations

from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.action.service import ActionRuntime
from van_gateway.models import ActionClass, PrincipalType


BUILTIN_ACTIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition(
        action_id="owner.context.read",
        action_class=ActionClass.A1,
        mutates_state=False,
        allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.HERMES_AGENT, PrincipalType.SYSTEM},
        verifier_type=VerifierType.STATE_PREDICATE,
    ),
    ActionDefinition(
        action_id="research.web.search",
        action_class=ActionClass.A2,
        mutates_state=False,
        allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.HERMES_AGENT},
        verifier_type=VerifierType.RECEIPT,
        max_age_seconds=300,
    ),
    ActionDefinition(
        action_id="google.gmail.draft",
        action_class=ActionClass.A3,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        max_age_seconds=300,
        parameter_schema={
            "required": ["thread_id", "body"],
            "properties": {"thread_id": "string", "body": "string"},
        },
    ),
    ActionDefinition(
        action_id="google.gmail.send",
        action_class=ActionClass.A4,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        no_stale_replay=True,
        max_age_seconds=30,
        parameter_schema={
            "required": ["draft_id"],
            "properties": {"draft_id": "string"},
        },
    ),
    ActionDefinition(
        action_id="google.calendar.reschedule",
        action_class=ActionClass.A4,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        no_stale_replay=True,
        max_age_seconds=30,
        parameter_schema={
            "required": ["event_id", "new_start_unix"],
            "properties": {"event_id": "string", "new_start_unix": "integer"},
        },
    ),
    ActionDefinition(
        action_id="google.notebook.note.create",
        action_class=ActionClass.A3,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        max_age_seconds=300,
        parameter_schema={
            "required": ["notebook_id", "title"],
            "properties": {"notebook_id": "string", "title": "string", "body": "string"},
        },
    ),
    ActionDefinition(
        action_id="google.notebook.enterprise.create",
        action_class=ActionClass.A3,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        max_age_seconds=300,
        parameter_schema={"required": ["title"], "properties": {"title": "string"}},
    ),
    ActionDefinition(
        action_id="google.notebook.enterprise.sources.add",
        action_class=ActionClass.A3,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        max_age_seconds=300,
        parameter_schema={
            "required": ["notebook_id", "sources"],
            "properties": {"notebook_id": "string", "sources": "array"},
        },
    ),
    ActionDefinition(
        action_id="google.notebook.enterprise.delete",
        action_class=ActionClass.A4,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        no_stale_replay=True,
        max_age_seconds=30,
        parameter_schema={"required": ["notebook_id"], "properties": {"notebook_id": "string"}},
    ),
    ActionDefinition(
        action_id="google.notebook.enterprise.sources.delete",
        action_class=ActionClass.A4,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.READ_BACK,
        no_stale_replay=True,
        max_age_seconds=30,
        parameter_schema={
            "required": ["notebook_id", "source_names"],
            "properties": {"notebook_id": "string", "source_names": "array"},
        },
    ),
    ActionDefinition(
        action_id="trading.halt",
        action_class=ActionClass.A4,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.DOMAIN_ATTESTATION,
        no_stale_replay=True,
        max_age_seconds=5,
    ),
    # GAP-F-001 — the owner saying "remember that my accountant is Thandi" now has a typed
    # action and a gateway-side executor (command/local_executors.py) rather than a route
    # (`POST /v1/context/facts`) with no producer. STATE_PREDICATE — the independent check
    # is the gateway re-reading its own owner-fact store after the write.
    ActionDefinition(
        action_id="memory.remember",
        action_class=ActionClass.A2,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.STATE_PREDICATE,
        max_age_seconds=300,
        parameter_schema={
            "required": ["subject", "predicate", "value"],
            "properties": {
                "subject": "string", "predicate": "string", "value": "string", "scope": "string",
            },
        },
    ),
    # GAP-F-001 — "record decision: ..." / "we decided ...". Same writer and check as
    # `memory.remember`, kept as its own action id so a decision is never confused with an
    # arbitrary remembered statement in the audit trail or the learning stores.
    ActionDefinition(
        action_id="memory.decision.record",
        action_class=ActionClass.A2,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.STATE_PREDICATE,
        max_age_seconds=300,
        parameter_schema={
            "required": ["decision"],
            "properties": {"decision": "string"},
        },
    ),
    # GAP-F-002 — reminders had two production routes (`POST /v1/reminders`,
    # `/v1/reminders/parse`) and no owner-side producer. STATE_PREDICATE — the independent
    # check is the gateway re-reading its own open-reminders table after the write.
    ActionDefinition(
        action_id="reminder.create",
        action_class=ActionClass.A2,
        mutates_state=True,
        allowed_principals={PrincipalType.OWNER_DEVICE},
        verifier_type=VerifierType.STATE_PREDICATE,
        max_age_seconds=300,
        parameter_schema={
            "required": ["text", "due_expression"],
            "properties": {"text": "string", "due_expression": "string"},
        },
    ),
    ActionDefinition(
        action_id="secret.exfiltrate",
        action_class=ActionClass.A5,
        mutates_state=True,
        allowed_principals=set(),
        verifier_type=VerifierType.NONE,
        enabled=False,
    ),
)


async def install_builtin_actions(runtime: ActionRuntime) -> None:
    for definition in BUILTIN_ACTIONS:
        await runtime.register(definition)