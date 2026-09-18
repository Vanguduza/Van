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