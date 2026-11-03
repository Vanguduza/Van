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


class RetainedCashRow(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    movement:dict
    original_statement_ref:str=Field(pattern='^[0-9a-f]{64}$')
    observed_at_ms:int
    received_at_ms:int

    @field_validator('movement')
    @classmethod
    def native_cash_only(cls,value):
        ctrader={'native_id','operation','delta','balance_after','equity_after','balance_version','occurred_at_ms','money_digits'}
        mt5={'native_id','operation','native_time_ms','profit','commission','swap','fee'}
        if set(value) not in (ctrader,mt5):raise ValueError('Original native cash fields required')
        return value


class RetainedCashHistory(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.retained-cash-history/1']=Field(alias='schema')
    view:Literal['FINANCIAL_HISTORY']
    alias:str
    lifecycle_id:str
    incarnation:str=Field(pattern='^[0-9a-f]{64}$')
    account_control_domain:str=Field(pattern='^[0-9a-f]{64}$')
    original_plan_ref:str=Field(pattern='^[0-9a-f]{64}$')
    cutoff_ref:str=Field(pattern='^[0-9a-f]{64}$')
    attribution:Literal['ORIGINAL_PHYSICAL_ACCOUNT_PRE_DELETION']
    generation_provenance:Literal['UNKNOWN']
    return_qualification:Literal['NOT_ISSUED']
    settlement_qualification:Literal['NOT_ISSUED']
    risk_capital_qualified:Literal[False]
    execution_authority:Literal[False]
    freshness:Literal['HISTORICAL']
    remaining_obligations:list[str]
    state:Literal['OBSERVED','NO_DATA','CONFLICT','UNOBSERVED','IN_PROGRESS','RECONCILIATION_REQUIRED']
    original_prefix_state:Literal['OBSERVED','CONFLICT']|None=None
    collection:Literal['MOVEMENTS','COVERAGE','CONFLICT']
    reason:str
    movements:list[RetainedCashRow]=Field(max_length=100)
    movement_count:int|None=Field(ge=0)
    truncated:bool
    next_cursor:str|None=Field(max_length=4096)
    scope_hash:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    snapshot_ref:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    query_ref:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    statement_ref:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    source_observed_at_ms:int|None=None
    coverage_windows:list[dict]|None=None
    conflicts:list[dict]|None=None


class AccountLifecycleState(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.account-lifecycle/1']=Field(alias='schema')
    alias:str
    operation_id:str
    device_id:str
    account_control_domain:str=Field(pattern='^[0-9a-f]{64}$')
    incarnation:str=Field(pattern='^[0-9a-f]{64}$')
    revision:int=Field(gt=0)
    variant:Literal['DELETE_GRACE','IMMEDIATE_DISCONNECT']='DELETE_GRACE'
    phase:Literal['DELETING','PENDING_ARCHIVE','RELINK_REQUIRED','ARCHIVED','DISCONNECTING','DISCONNECTED']
    created_at_unix:int
    archive_at_unix:int|None
    grace_seconds:int|None=Field(gt=0)
    strategies:list[str]
    history_ref:str=Field(pattern='^[0-9a-f]{64}$')
    credential_disposition:Literal['DELETE_MANAGED','NONE']
    detached:Literal[True]
    link_intent:Literal['RELINK_REQUIRED']
    remote_account_closed:Literal[False]
    record_digest:str=Field(pattern='^[0-9a-f]{64}$')
    financial_history_retained:Literal[True]
    execution_authority:Literal[False]
    native_original_phase:Literal['IN_FLIGHT','APPLIED','REFUSED','UNKNOWN']|None=None
    metadata_hold:Literal['ORIGINAL_OUTCOME_REQUIRES_RECONCILIATION']|None=None

    @model_validator(mode='after')
    def coherent_lifecycle_timing(self):
        immediate=self.phase in {'DISCONNECTING','DISCONNECTED'}
        if immediate!=(self.variant=='IMMEDIATE_DISCONNECT'):
            raise ValueError('Lifecycle phase and original variant differ')
        if immediate:
            if self.archive_at_unix is not None or self.grace_seconds is not None:
                raise ValueError('Immediate disconnect has no grace or archive deadline')
        elif (self.archive_at_unix is None or self.grace_seconds is None
              or self.archive_at_unix!=self.created_at_unix+self.grace_seconds):
            raise ValueError('Deletion needs original explicit grace and archive deadline')
        return self

    @model_serializer(mode='wrap')
    def preserve_native_data_body(self,handler):
        data=handler(self)
        for key in ('native_original_phase','metadata_hold'):
            if getattr(self,key) is None:data.pop(key,None)
        return data

class LifecycleSessionSource(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    source_ref:str=Field(pattern='^[0-9a-f]{64}$')
    sha256:str=Field(pattern='^[0-9a-f]{64}$')
    account_alias:str

class LifecycleDeleteView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    variant:Literal['DELETE_GRACE','IMMEDIATE_DISCONNECT']
    grace_seconds:int|None=Field(gt=0)
    strategies:list[str]
    session_sources:list[LifecycleSessionSource]
    unlink_review:AccountResolvedReview
    incarnation:str=Field(pattern='^[0-9a-f]{64}$')
    account_control_domain:str=Field(pattern='^[0-9a-f]{64}$')
    owner_device_id:str
    credential_disposition:Literal['DELETE_MANAGED','NONE']
    prior_lifecycle:AccountLifecycleState|None=None

    @model_validator(mode='after')
    def coherent_variant(self):
        if (self.variant=='IMMEDIATE_DISCONNECT')!=(self.grace_seconds is None):
            raise ValueError('Immediate disconnect has no deletion grace')
        if not self.session_sources:raise ValueError('Native session scope must be explicit and nonempty')
        return self

    @model_serializer(mode='wrap')
    def preserve_original_review_body(self,handler):
        data=handler(self)
        if self.prior_lifecycle is None:data.pop('prior_lifecycle',None)
        return data

class LifecycleRemoteState(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    state:Literal['NOT_APPLICABLE','OPEN']
    source_ref:str=Field(pattern='^[0-9a-f]{64}$')

class LifecycleCancelView(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    variant:Literal['CANCEL_DELETE']
    original:AccountLifecycleState
    remote_state:LifecycleRemoteState
    account_control_domain:str=Field(pattern='^[0-9a-f]{64}$')
    owner_device_id:str

class AccountLifecycleReview(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_name:Literal['vati.account-lifecycle-review/1']=Field(alias='schema')
    action:Literal['account_remove']
    alias:str
    resource_version:str=Field(pattern='^[0-9a-f]{64}$')
    semantic_digest:str=Field(pattern='^[0-9a-f]{64}$')
    view:LifecycleDeleteView|LifecycleCancelView
    context_digest:str=Field(pattern='^[0-9a-f]{64}$')
    request_digest:str=Field(pattern='^[0-9a-f]{64}$')
    review_digest:str=Field(pattern='^[0-9a-f]{64}$')

class AccountChallengeResponse(BaseModel):
    approval_challenge_id: str
    approval_challenge: str
    issued_at_unix: int
    approval_expires_at_unix: int
    resolved_action_id: str
    resolved_review: AccountResolvedReview | AccountCleanupReview | AccountLifecycleReview | None=None
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
