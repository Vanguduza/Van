"""Public owner contracts; native credential locators and values stay private."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StrictStr,StrictBool


class CredentialReferenceSummary(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind: Literal['none','file','env']


class PublicAccountRecord(BaseModel):
    model_config=ConfigDict(extra='forbid')
    alias: StrictStr
    broker: StrictStr
    mode: StrictStr
    currency: StrictStr
    label: StrictStr
    server: StrictStr
    login: StrictStr
    venue: StrictStr
    bridge_url: StrictStr
    credential_ref: CredentialReferenceSummary
    demo: StrictBool
    enabled: StrictBool
    mandate_ref: StrictStr
    notes: StrictStr
    safety_identity: StrictStr


class AccountResolvedReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_name: Literal['vati.account-review/1']=Field(alias='schema')
    action: Literal['account_upsert']
    alias: StrictStr
    request_digest: str=Field(pattern='^[0-9a-f]{64}$')
    resource_version: str=Field(pattern='^[0-9a-f]{64}$')
    review_digest: str=Field(pattern='^[0-9a-f]{64}$')
    before: PublicAccountRecord | None
    after: PublicAccountRecord
    changed_fields: list[str]


class AccountChallengeResponse(BaseModel):
    approval_challenge_id: str
    approval_challenge: str
    issued_at_unix: int
    approval_expires_at_unix: int
    resolved_action_id: str
    resolved_review: AccountResolvedReview | None=None


class AccountActionDefinition(BaseModel):
    action: str
    requires_owner_approval: bool
    requires_resolved_review: bool
    supports_original_operation_readback: bool
    input_schema: dict


class AccountActionCatalog(BaseModel):
    schema_name: Literal['van.account-actions/1']=Field(alias='schema')
    actions: list[AccountActionDefinition]
    credential_keys_by_broker: dict[str,list[str]]
