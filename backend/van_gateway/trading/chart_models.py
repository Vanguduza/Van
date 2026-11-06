"""Renderer-independent owner chart settings, with no trading authority."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Identity = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]
NativeIdentity = Annotated[str, StringConstraints(strict=True,min_length=1,max_length=256,pattern=r'^[^\x00-\x1f\x7f]+$')]
Price = Annotated[str, StringConstraints(strict=True, max_length=80, pattern=r'^-?[0-9]+(?:\.[0-9]+)?$')]
Timestamp = Annotated[int, Field(strict=True, ge=0, le=253402300799000)]
Period = Annotated[int, Field(strict=True, ge=1, le=2000)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_default=True)
    @model_validator(mode='before')
    @classmethod
    def exact_schema_version(cls,value):
        if isinstance(value,dict) and 'schema_version' in value and type(value['schema_version']) is not int:
            raise ValueError('schema version must be an integer')
        return value

class InstrumentRef(StrictModel):
    venue: Identity
    environment: Literal['LIVE','DEMO','HISTORICAL']
    api_family: Identity
    product_id: NativeIdentity
    symbol: NativeIdentity
    account_id: NativeIdentity | None = None
    contract_revision: Identity | None = None
    @field_validator('product_id','symbol','account_id')
    @classmethod
    def native_nonempty(cls,value):
        if value is not None and not value.strip():raise ValueError('empty native identity')
        return value

class PeriodIndicator(StrictModel):
    kind: Literal['SMA','EMA','RSI','ATR']
    period: Period

class MacdIndicator(StrictModel):
    kind: Literal['MACD']
    fast: Period = 12
    slow: Period = 26
    signal: Period = 9
    @model_validator(mode='after')
    def ordered(self):
        if self.fast >= self.slow:raise ValueError('MACD fast period must be less than slow period')
        return self

class BollingerIndicator(StrictModel):
    kind: Literal['BOLLINGER']
    period: Period = 20
    deviations: Price = '2'
    @field_validator('deviations')
    @classmethod
    def bounded(cls,value):
        if not Decimal('0') < Decimal(value) <= Decimal('10'):raise ValueError('invalid deviation multiplier')
        return value

class VwapIndicator(StrictModel):
    kind: Literal['VWAP']
    anchor_ms: Timestamp

IndicatorSpec = Annotated[PeriodIndicator | MacdIndicator | BollingerIndicator | VwapIndicator, Field(discriminator='kind')]

class IndicatorInstance(StrictModel):
    indicator_id: Identity
    schema_version: Literal[1] = 1
    spec: IndicatorSpec
    pane: Literal['PRICE','SEPARATE'] = 'PRICE'
    source_timeframe: Literal['M1','M5','M15','M30','H1','H4','D1']
    provenance_tier: Literal['PRESENTATION','RESEARCH'] = 'PRESENTATION'
    visible: bool = Field(default=True,strict=True)

class Anchor(StrictModel):
    time_ms: Timestamp
    price: Price

class DrawingRecord(StrictModel):
    drawing_id: Identity
    schema_version: Literal[1] = 1
    kind: Literal['LEVEL','TREND','CHANNEL','FIBONACCI','RISK_REWARD','NOTE']
    anchors: list[Anchor] = Field(min_length=1,max_length=3)
    note: Annotated[str,StringConstraints(strict=True,max_length=4000)] = ''
    @model_validator(mode='after')
    def anchor_count(self):
        required={'LEVEL':1,'TREND':2,'CHANNEL':3,'FIBONACCI':2,'RISK_REWARD':3,'NOTE':1}[self.kind]
        if len(self.anchors)!=required:raise ValueError('wrong number of price/time anchors for drawing')
        if self.kind in {'TREND','FIBONACCI'} and self.anchors[0].time_ms==self.anchors[1].time_ms:
            raise ValueError('drawing requires distinct time anchors')
        return self

class Viewport(StrictModel):
    start_ms: Timestamp
    end_ms: Timestamp
    min_price: Price | None = None
    max_price: Price | None = None
    @model_validator(mode='after')
    def bounds(self):
        if self.start_ms >= self.end_ms:raise ValueError('invalid viewport time range')
        if (self.min_price is None)!=(self.max_price is None):raise ValueError('price bounds must be paired')
        if self.min_price is not None and Decimal(self.min_price)>=Decimal(self.max_price):raise ValueError('invalid viewport price range')
        return self

class ChartPanel(StrictModel):
    panel_id: Identity
    instrument: InstrumentRef
    timeframe: Literal['M1','M5','M15','M30','H1','H4','D1']
    chart_type: Literal['CANDLES','LINE','AREA','HEIKIN_ASHI'] = 'CANDLES'
    viewport: Viewport | None = None
    indicators: list[IndicatorInstance] = Field(default_factory=list,max_length=64)
    drawings: list[DrawingRecord] = Field(default_factory=list,max_length=256)
    @model_validator(mode='after')
    def unique_children(self):
        for rows,key in [(self.indicators,'indicator_id'),(self.drawings,'drawing_id')]:
            ids=[getattr(row,key) for row in rows]
            if len(ids)!=len(set(ids)):raise ValueError('duplicate chart child identity')
        return self

class WorkspaceState(StrictModel):
    schema_version: Literal[1] = 1
    name: Annotated[str,StringConstraints(strict=True,min_length=1,max_length=160)]
    layout: Literal['SINGLE','SPLIT_HORIZONTAL','SPLIT_VERTICAL','GRID'] = 'SINGLE'
    panels: list[ChartPanel] = Field(min_length=1,max_length=8)
    selected_panel_id: Identity
    sync_time: bool = Field(default=False,strict=True)
    @field_validator('name')
    @classmethod
    def name_text(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 for c in value):raise ValueError('invalid workspace name')
        return value
    @model_validator(mode='after')
    def selected(self):
        ids=[p.panel_id for p in self.panels]
        if len(ids)!=len(set(ids)) or self.selected_panel_id not in ids:raise ValueError('invalid selected or duplicate panel')
        if self.layout=='SINGLE' and len(ids)!=1:raise ValueError('single layout requires exactly one panel')
        if self.layout.startswith('SPLIT_') and len(ids)!=2:raise ValueError('split layout requires exactly two panels')
        return self

class CreateWorkspace(StrictModel):
    request_id: Identity
    state: WorkspaceState

class ReplaceWorkspace(CreateWorkspace):
    expected_revision: int = Field(strict=True,ge=1,le=1024)

class RestoreWorkspace(StrictModel):
    request_id: Identity
    expected_revision: int = Field(strict=True,ge=1,le=1024)
    target_revision: int = Field(strict=True,ge=1,le=1024)

class DeleteWorkspace(StrictModel):
    request_id: Identity
    expected_revision: int = Field(strict=True,ge=1,le=1024)

class WorkspaceWrite(StrictModel):
    request_id: str
    workspace_id: str
    revision: int
    state_sha256: str | None
    status: Literal['SAVED','DELETED']
    authority_effect: Literal['NONE'] = 'NONE'

class WorkspaceRevision(StrictModel):
    workspace_id: str
    revision: int
    state: WorkspaceState
    state_sha256: str
    recorded_at_ms: int
    restored_from_revision: int | None = None
    authority_effect: Literal['NONE'] = 'NONE'
    instrument_scope_status: Literal['OWNER_SELECTION_NOT_NATIVE_VERIFIED'] = 'OWNER_SELECTION_NOT_NATIVE_VERIFIED'

class WorkspaceSummary(StrictModel):
    workspace_id: str
    revision: int
    name: str
    updated_at_ms: int

class WorkspaceList(StrictModel):
    workspaces: list[WorkspaceSummary]
    total_count: int
    next_after_id: str | None

class RevisionSummary(StrictModel):
    revision: int
    state_sha256: str
    recorded_at_ms: int
    restored_from_revision: int | None

class RevisionList(StrictModel):
    workspace_id: str
    revisions: list[RevisionSummary]
    total_count: int
    next_before_revision: int | None

class ChartCapability(StrictModel):
    schema_version: Literal[1] = 1
    authority_effect: Literal['NONE'] = 'NONE'
    coordinate_system: Literal['UTC_MILLISECONDS_AND_EXACT_DECIMAL_PRICE'] = 'UTC_MILLISECONDS_AND_EXACT_DECIMAL_PRICE'
    workspace_versioning: Literal['EXPECTED_REVISION_WITH_EXPLICIT_CONFLICT'] = 'EXPECTED_REVISION_WITH_EXPLICIT_CONFLICT'
    history: Literal['IMMUTABLE_SNAPSHOTS_RESTORE_AS_NEW_REVISION'] = 'IMMUTABLE_SNAPSHOTS_RESTORE_AS_NEW_REVISION'
    chart_types: list[str] = ['CANDLES','LINE','AREA','HEIKIN_ASHI']
    timeframes: list[str] = ['M1','M5','M15','M30','H1','H4','D1']
    indicator_provenance_tiers: list[str] = ['PRESENTATION','RESEARCH']
    indicator_kinds: list[str] = ['SMA','EMA','RSI','ATR','MACD','BOLLINGER','VWAP']
    drawing_kinds: list[str] = ['LEVEL','TREND','CHANNEL','FIBONACCI','RISK_REWARD','NOTE']
    max_state_bytes: int = 262144
    max_workspaces: int = 128
    max_revisions: int = 1024
    qualified_vati_indicator_calculation: bool = False
    renderer_qualification: bool = False
    native_instrument_binding: bool = False

class ChartErrorDetails(StrictModel):
    code: str
    request_id: str | None = None
    current_revision: int | None = None

class ChartErrorResponse(StrictModel):
    detail: ChartErrorDetails
