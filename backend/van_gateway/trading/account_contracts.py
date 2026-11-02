"""Public owner contracts; native credential locators and values stay private."""
from typing import Literal
from decimal import Decimal
from pydantic import BaseModel,ConfigDict,Field,StrictStr,StrictBool,model_validator,model_serializer,field_validator


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


class RetainedRemoteFunds(BaseModel):
    model_config=ConfigDict(extra='forbid')
    balance: StrictStr
    equity: StrictStr
    currency: StrictStr

    @field_validator('balance','equity')
    @classmethod
    def finite_money(cls,value):
        try:
            if not Decimal(value).is_finite():raise ValueError('native money must be finite')
        except ArithmeticError:raise ValueError('native money must be finite') from None
        return value


class AccountRetirementReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_name: Literal['vati.local-unlink-review/1']=Field(alias='schema')
    remote_account_closed: Literal[False]
    historical_data_retained: Literal[True]
    retained_remote_funds: RetainedRemoteFunds | None
    trade_history_ref: str=Field(pattern='^[0-9a-f]{64}$')
    trade_history_count: int=Field(ge=0)
    credential_cleanup: Literal['DELETE_MANAGED','KEEP_SHARED','KEEP_EXTERNAL','NONE']


class AccountResolvedReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_name: Literal['vati.account-review/1']=Field(alias='schema')
    action: Literal['account_upsert','account_remove']
    alias: StrictStr
    request_digest: str=Field(pattern='^[0-9a-f]{64}$')
    resource_version: str=Field(pattern='^[0-9a-f]{64}$')
    review_digest: str=Field(pattern='^[0-9a-f]{64}$')
    before: PublicAccountRecord | None
    after: PublicAccountRecord | None
    changed_fields: list[str]
    retirement: AccountRetirementReview | None=None

    @model_validator(mode='after')
    def coherent_action(self):
        if self.action=='account_upsert':
            if self.after is None or self.retirement is not None:raise ValueError('account edit review is incomplete')
        elif self.before is None or self.after is not None or self.retirement is None or self.changed_fields!=['local_link']:
            raise ValueError('local unlink needs exact before and retained-funds review')
        elif ((self.retirement.retained_remote_funds is None)!=(self.before.broker=='PAPER')
              or (self.retirement.retained_remote_funds is not None
                  and self.retirement.retained_remote_funds.currency!=self.before.currency)):
            raise ValueError('local unlink needs known funds in the bound account currency')
        return self

    @model_serializer(mode='wrap')
    def preserve_native_review_body(self,handler):
        values=handler(self)
        # The signature/digest covers the native wire object. A response-model
        # default must not insert a new null field into an existing edit review.
        if self.action=='account_upsert':values.pop('retirement',None)
        return values


class CleanupOriginalAccount(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    alias:str
    broker:str
    server:str
    login:str
    currency:str
    demo:bool
    safety_identity:str


class CleanupLocalState(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    registry:Literal['ORIGINAL_PRESENT','ORIGINAL_LINK_ABSENT_NOT_ORIGINAL_COMPLETION']
    credential:Literal['NOT_MANAGED','ORIGINAL_MANAGED_FILE','ORIGINAL_OWN_OVERWRITE_UNUSABLE_FOR_NEW_NATIVE_OBSERVATION',
                       'ORIGINAL_UNLINK_FACT_AND_CURRENT_ABSENCE_NOT_PROVIDER_STATE']


class CleanupView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    parent_operation_id:str=Field(pattern='^[A-Za-z0-9_-]{20,128}$')
    plan_ref:str=Field(pattern='^[0-9a-f]{64}$')
    original_device_id:str
    account_control_domain:str=Field(pattern='^[0-9a-f]{64}$')
    alias:str
    original_epoch:int=Field(ge=1)
    original_account:CleanupOriginalAccount
    current_local_state:CleanupLocalState
    original_step_head_ref:str=Field(pattern='^[0-9a-f]{64}$')
    target_state_digest:str=Field(pattern='^[0-9a-f]{64}$')
    remaining_steps:list[Literal['REGISTRY_REMOVE','CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK']]
    retire_parent_safety_obligation:bool
    retirement:AccountRetirementReview
    parent_original_state:Literal['UNKNOWN']
    parent_original_result:None
    provider_closure_authority:Literal[False]


class AccountCleanupReview(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.pending-account-cleanup-review/1']=Field(alias='schema')
    action:Literal['account_remove']
    variant:Literal['PENDING_CLEANUP']
    request_digest:str=Field(pattern='^[0-9a-f]{64}$')
    resource_version:str=Field(pattern='^[0-9a-f]{64}$')
    context_digest:str=Field(pattern='^[0-9a-f]{64}$')
    review_digest:str=Field(pattern='^[0-9a-f]{64}$')
    view:CleanupView


class AccountChallengeResponse(BaseModel):
    approval_challenge_id: str
    approval_challenge: str
    issued_at_unix: int
    approval_expires_at_unix: int
    resolved_action_id: str
    resolved_review: AccountResolvedReview | AccountCleanupReview | None=None
    account_control_domain: str=Field(pattern='^[0-9a-f]{64}$')


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
    account_control_domain: str=Field(pattern='^[0-9a-f]{64}$')


class CleanupStepFact(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    state:Literal['MAY_BEGIN','DONE','VERIFIED_ABSENT']
    epoch:int=Field(ge=1)
    executor_operation_id:str


class AccountCleanupSummary(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.pending-local-cleanup/1']=Field(alias='schema')
    state:Literal['PROSPECTIVE_PLAN_RETAINED','QUALIFIED_SEPARATE_RESOLUTION']
    plan_ref:str=Field(pattern='^[0-9a-f]{64}$')
    epoch:int=Field(ge=1)
    parent_operation_id:str
    parent_phase:Literal['IN_FLIGHT','APPLIED','REFUSED','UNKNOWN']
    step_facts:dict[Literal['REGISTRY_REMOVE','CREDENTIAL_OVERWRITE','CREDENTIAL_UNLINK'],CleanupStepFact]
    linked_resolution_ref:str|None
    linked_resolution_child_operation_id:str|None
    linked_child_applied_ref:str|None
    parent_original_unchanged:Literal[True]
    execution_authority:Literal[False]
