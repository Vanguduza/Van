"""Owner market monitor contracts. Configuration never grants execution authority."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, StringConstraints, field_validator, model_validator
from .chart_models import (StrictModel, Identity, InstrumentRef, Price, Timestamp,
                           IndicatorSpec, DrawingRecord)

Name = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=160)]
Keyword = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
ComputedValue = Annotated[str, StringConstraints(strict=True, max_length=256, pattern=r'^-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$')]
Timeframe = Literal['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']
Comparator = Literal['AT_OR_ABOVE', 'AT_OR_BELOW', 'CROSS_ABOVE', 'CROSS_BELOW']


class WatchlistEntry(StrictModel):
    instrument: InstrumentRef
    favourite: bool = Field(default=False, strict=True)


class WatchlistState(StrictModel):
    name: Name
    entries: list[WatchlistEntry] = Field(default_factory=list, max_length=128)
    sort_by: Literal['MANUAL', 'SYMBOL', 'PRICE', 'CHANGE_PCT', 'SPREAD'] = 'MANUAL'
    descending: bool = Field(default=False, strict=True)
    favourites_only: bool = Field(default=False, strict=True)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('name must contain visible text without controls')
        return value.strip()

    @model_validator(mode='after')
    def unique_native_instruments(self):
        keys = [e.instrument.model_dump_json() for e in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate instrument identity')
        return self


class PriceCondition(StrictModel):
    basis: Literal['CLOSED_BAR_CLOSE'] = 'CLOSED_BAR_CLOSE'
    kind: Literal['PRICE']
    comparator: Comparator
    threshold: Price


class IndicatorCondition(StrictModel):
    kind: Literal['INDICATOR']
    indicator: IndicatorSpec
    component: Literal['VALUE', 'MACD', 'SIGNAL', 'HISTOGRAM', 'UPPER', 'MIDDLE', 'LOWER'] = 'VALUE'
    comparator: Comparator
    threshold: Price

    @model_validator(mode='after')
    def valid_component(self):
        accepted = ({'MACD', 'SIGNAL', 'HISTOGRAM'} if self.indicator.kind == 'MACD'
                    else {'UPPER', 'MIDDLE', 'LOWER'} if self.indicator.kind == 'BOLLINGER'
                    else {'VALUE'})
        if self.component not in accepted:
            raise ValueError('component does not belong to indicator')
        return self


class DrawingCondition(StrictModel):
    kind: Literal['DRAWING']
    drawing: DrawingRecord
    comparator: Literal['CROSS_ABOVE', 'CROSS_BELOW']

    @model_validator(mode='after')
    def evaluable_drawing(self):
        if self.drawing.kind not in {'LEVEL', 'TREND'}:
            raise ValueError('crossing requires a pinned level or trend line')
        return self


class NewsCondition(StrictModel):
    kind: Literal['NEWS']
    keywords: list[Keyword] = Field(min_length=1, max_length=16)
    match: Literal['ANY', 'ALL'] = 'ANY'
    minimum_trust: Literal['T1_PRIMARY', 'T2_SECONDARY'] = 'T2_SECONDARY'

    @field_validator('keywords')
    @classmethod
    def literal_keywords(cls, values):
        values = [v.strip().casefold() for v in values]
        if any(not v or any(ord(c) < 32 for c in v) for v in values) or len(values) != len(set(values)):
            raise ValueError('keywords must be distinct visible literal text')
        return values


TechnicalCondition = Annotated[PriceCondition | IndicatorCondition | DrawingCondition,
                               Field(discriminator='kind')]
AlertCondition = Annotated[PriceCondition | IndicatorCondition | DrawingCondition | NewsCondition,
                           Field(discriminator='kind')]


class AlertState(StrictModel):
    name: Name
    condition: AlertCondition
    instrument: InstrumentRef | None = None
    timeframe: Timeframe = 'M1'
    max_age_ms: int = Field(default=120000, strict=True, ge=1000, le=86400000)

    _name_text = field_validator('name')(WatchlistState.nonblank_name.__func__)

    @model_validator(mode='after')
    def technical_identity(self):
        if self.condition.kind != 'NEWS' and self.instrument is None:
            raise ValueError('technical alert requires complete instrument identity')
        return self


class CreateWatchlist(StrictModel):
    request_id: Identity
    state: WatchlistState


class ReplaceWatchlist(CreateWatchlist):
    expected_revision: int = Field(strict=True, ge=1)


class CreateAlert(StrictModel):
    request_id: Identity
    state: AlertState


class ReplaceAlert(CreateAlert):
    expected_revision: int = Field(strict=True, ge=1)


class MonitorControl(StrictModel):
    request_id: Identity
    expected_revision: int = Field(strict=True, ge=1)


class MonitorWrite(StrictModel):
    request_id: str
    object_id: str
    kind: Literal['WATCHLIST', 'ALERT', 'SCREEN_RULE']
    revision: int
    state_sha256: str | None
    status: Literal['SAVED', 'PAUSED', 'RESTARTED', 'DELETED']
    authority_effect: Literal['NONE'] = 'NONE'


class EvaluationStatus(StrictModel):
    state: Literal['NOT_EVALUATED', 'UNAVAILABLE', 'BASELINE', 'NO_MATCH', 'TRIGGERED']
    reason: str
    evaluated_at_ms: Timestamp
    clock_high_water_ms: Timestamp | None = None
    measurement_basis: Literal["CLOSED_BAR_CLOSE", "INDICATOR_ON_CLOSED_BARS", "PINNED_DRAWING_ON_CLOSED_BARS", "RECORDED_NEWS"] | None = None
    sample_id: str | None = None
    source_id: str | None = None
    source_revision: str | None = None
    event_time_ms: Timestamp | None = None
    available_at_ms: Timestamp | None = None
    value: ComputedValue | None = None
    event_id: str | None = None


class WatchlistView(StrictModel):
    object_id: str
    kind: Literal['WATCHLIST'] = 'WATCHLIST'
    revision: int
    state: WatchlistState
    state_sha256: str
    updated_at_ms: Timestamp
    authority_effect: Literal['NONE'] = 'NONE'
    instrument_binding: Literal['OWNER_SELECTION_NOT_NATIVE_VERIFIED'] = 'OWNER_SELECTION_NOT_NATIVE_VERIFIED'


class AlertView(StrictModel):
    object_id: str
    kind: Literal['ALERT'] = 'ALERT'
    revision: int
    state: AlertState
    state_sha256: str
    lifecycle: Literal['ACTIVE', 'PAUSED', 'TRIGGERED']
    arm_generation: int
    armed_at_ms: Timestamp
    updated_at_ms: Timestamp
    evaluation: EvaluationStatus | None
    authority_effect: Literal['NONE'] = 'NONE'


class WatchlistPage(StrictModel):
    items: list[WatchlistView]
    total_count: int
    next_after_id: str | None


class WatchlistMarketRequest(StrictModel):
    expected_revision: int = Field(strict=True, ge=1)
    timeframe: Timeframe = 'M1'
    max_age_ms: int = Field(default=120000, strict=True, ge=1000, le=86400000)
    search: Annotated[str, StringConstraints(strict=True, max_length=160)] = ''
    venue: Identity | None = None
    environment: Literal['LIVE', 'DEMO', 'HISTORICAL'] | None = None
    api_family: Identity | None = None

    @field_validator('search')
    @classmethod
    def visible_search(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('search cannot contain control characters')
        return value.strip()


class WatchlistMarketRow(StrictModel):
    instrument: InstrumentRef
    favourite: bool
    manual_index: int
    state: Literal['AVAILABLE', 'UNAVAILABLE']
    reason: str
    evaluated_at_ms: Timestamp
    measurement_basis: Literal['CLOSED_BAR_CLOSE'] = 'CLOSED_BAR_CLOSE'
    price: Price | None = None
    price_age_ms: int | None = None
    event_time_ms: Timestamp | None = None
    available_at_ms: Timestamp | None = None
    sample_id: str | None = None
    source_id: str | None = None
    source_revision: str | None = None
    change_basis: Literal['PREVIOUS_CONTIGUOUS_BAR'] = 'PREVIOUS_CONTIGUOUS_BAR'
    change_state: Literal['AVAILABLE', 'HISTORY_UNAVAILABLE', 'ZERO_REFERENCE', 'SOURCE_UNAVAILABLE']
    change_pct: ComputedValue | None = None
    reference_price: Price | None = None
    reference_time_ms: Timestamp | None = None
    change_interval_ms: int | None = None
    spread: None = None
    spread_state: Literal['NOT_REPORTED_IN_CLOSED_BAR_SOURCE'] = 'NOT_REPORTED_IN_CLOSED_BAR_SOURCE'


class WatchlistMarketResult(StrictModel):
    object_id: str
    revision: int
    state_sha256: str
    request: WatchlistMarketRequest
    sort_by: Literal['MANUAL', 'SYMBOL', 'PRICE', 'CHANGE_PCT', 'SPREAD']
    descending: bool
    favourites_only: bool
    sort_metric_state: Literal['AVAILABLE', 'PARTIAL', 'UNAVAILABLE', 'NOT_APPLICABLE']
    selected_count: int
    filtered_count: int
    rows: list[WatchlistMarketRow]
    evaluated_at_ms: Timestamp
    authority_effect: Literal['NONE'] = 'NONE'


class AlertPage(StrictModel):
    items: list[AlertView]
    total_count: int
    next_after_id: str | None


class ScanPriceCondition(PriceCondition):
    comparator: Literal['AT_OR_ABOVE', 'AT_OR_BELOW']


class ScanIndicatorCondition(IndicatorCondition):
    comparator: Literal['AT_OR_ABOVE', 'AT_OR_BELOW']


ScanCondition = Annotated[ScanPriceCondition | ScanIndicatorCondition, Field(discriminator='kind')]


class ScreenRequest(StrictModel):
    instruments: list[InstrumentRef] = Field(min_length=1, max_length=64)
    timeframe: Timeframe = 'M1'
    conditions: list[ScanCondition] = Field(min_length=1, max_length=4)
    max_age_ms: int = Field(default=120000, strict=True, ge=1000, le=86400000)

    @model_validator(mode='after')
    def closed_scan(self):
        ids = [i.model_dump_json() for i in self.instruments]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate scan instrument')
        if any(c.comparator.startswith('CROSS_') for c in self.conditions):
            raise ValueError('screening uses level predicates, not unobserved crossings')
        return self


class ScreenRuleState(ScreenRequest):
    name: Name
    _name_text = field_validator('name')(WatchlistState.nonblank_name.__func__)


class CreateScreenRule(StrictModel):
    request_id: Identity
    state: ScreenRuleState


class ReplaceScreenRule(CreateScreenRule):
    expected_revision: int = Field(strict=True, ge=1)


class RunScreenRule(StrictModel):
    expected_revision: int = Field(strict=True, ge=1)


class ScreenRuleView(StrictModel):
    object_id: str
    kind: Literal['SCREEN_RULE'] = 'SCREEN_RULE'
    revision: int
    state: ScreenRuleState
    state_sha256: str
    updated_at_ms: Timestamp
    authority_effect: Literal['NONE'] = 'NONE'


class ScreenRulePage(StrictModel):
    items: list[ScreenRuleView]
    total_count: int
    next_after_id: str | None


class ScreenRuleBinding(StrictModel):
    object_id: str
    revision: int
    state_sha256: str


class ScreenRow(StrictModel):
    instrument: InstrumentRef
    state: Literal['MATCH', 'NO_MATCH', 'UNAVAILABLE']
    reason: str
    evaluated_at_ms: Timestamp
    price_age_ms: int | None
    values: list[ComputedValue] = Field(default_factory=list)
    sample_id: str | None = None


class ScreenResult(StrictModel):
    saved_rule: ScreenRuleBinding | None = None
    evaluated_at_ms: Timestamp
    rows: list[ScreenRow]
    authority_effect: Literal['NONE'] = 'NONE'


class MonitorCapabilities(StrictModel):
    schema_version: Literal[1] = 1
    authority_effect: Literal['NONE'] = 'NONE'
    max_watchlists: int = 128
    max_alerts: int = 128
    max_screen_rules: int = 128
    max_entries_per_watchlist: int = 128
    max_state_bytes: int = 131072
    max_scan_instruments: int = 64
    scan_instruments_per_minute: int = 256
    alert_mode: Literal['ONE_TRIGGER_PER_EXPLICIT_ARM_GENERATION'] = 'ONE_TRIGGER_PER_EXPLICIT_ARM_GENERATION'
    technical_observation_basis: Literal['CLOSED_BARS_ONLY_NATIVE_QUOTES_PENDING'] = 'CLOSED_BARS_ONLY_NATIVE_QUOTES_PENDING'
    technical_source_binding: Literal['UNAVAILABLE_BAR_LAKE_HAS_NO_FULL_NATIVE_IDENTITY'] = 'UNAVAILABLE_BAR_LAKE_HAS_NO_FULL_NATIVE_IDENTITY'
    news_source: Literal['LAST_500_RECORDED_LEDGER_HEADLINES_DECLARED_SOURCE_TRUST'] = 'LAST_500_RECORDED_LEDGER_HEADLINES_DECLARED_SOURCE_TRUST'
    indicator_calculation_qualified: bool = False
    push_notification_delivery_qualified: bool = False
    dynamic_watchlists_qualified: bool = False
    formal_unit_acceptance: Literal['NOT_ISSUED'] = 'NOT_ISSUED'


class MonitorErrorDetails(StrictModel):
    code: str
    current_revision: int | None = None
    request_id: str | None = None
    retry_after_ms: int | None = None


class MonitorErrorResponse(StrictModel):
    detail: MonitorErrorDetails
