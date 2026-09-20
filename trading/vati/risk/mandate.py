"""Owner Trading Mandate (Rev 2 §38).

A mandate is an owner-signed, versioned capability grant. It is the top of the
trading authority order. The Risk Authority enforces it; nothing may exceed it.
Platform ceilings sit *beneath* the mandate as a fail-closed floor: a mandate
that asks for more than the ceiling is rejected at load time, never widened.
"""

from __future__ import annotations

import time

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping
from vati.authority import (
    MAX_STANDING_LIFETIME_SECONDS,
    OwnerAuthorityError,
    OwnerAuthorityVerifier,
)


class MandateError(ValueError):
    """Raised when a mandate is malformed, unsigned, expired or exceeds ceilings."""


class AuthorizationMode(str, Enum):
    OBSERVE = "OBSERVE"
    ADVISOR = "ADVISOR"
    DEMO_TRADER = "DEMO_TRADER"
    SHADOW_TRADER = "SHADOW_TRADER"
    LIMITED_LIVE = "LIMITED_LIVE"
    AUTONOMOUS_LIVE = "AUTONOMOUS_LIVE"
    HALTED = "HALTED"


ORDER_SENDING_MODES = frozenset(
    {AuthorizationMode.DEMO_TRADER, AuthorizationMode.LIMITED_LIVE, AuthorizationMode.AUTONOMOUS_LIVE}
)
LIVE_MONEY_MODES = frozenset({AuthorizationMode.LIMITED_LIVE, AuthorizationMode.AUTONOMOUS_LIVE})

# Rev 2 §39 — behaviours a mandate can never permit. A mandate that omits any of
# these from its forbidden list is invalid; the list is a floor, not a menu.
HARD_FORBIDDEN_BEHAVIOURS = frozenset(
    {
        "martingale",
        "unlimited_grid",
        "unlimited_averaging_down",
        "stop_removal",
        "stop_widening_on_loss",
        "revenge_risk_increase",
        "risk_doubling_after_loss",
        "trade_without_broker_side_stop",
        "trade_unverified_account",
        "trade_stale_data",
        "duplicate_order",
        "silent_strategy_mutation",
        "unvalidated_research_to_live",
        "unbounded_leverage",
        "single_dom_as_total_fx_liquidity",
        "macro_causality_on_synthetics",
    }
)


@dataclass(frozen=True)
class PlatformCeilings:
    """Fail-closed ceilings a mandate may not exceed. Changing them is an
    owner-signed A4 action recorded as a new risk policy version."""

    max_risk_per_trade: Decimal = Decimal("0.0200")
    max_open_stop_risk: Decimal = Decimal("0.0600")
    max_daily_loss: Decimal = Decimal("0.0500")
    max_weekly_drawdown: Decimal = Decimal("0.1000")
    max_currency_leg_exposure: Decimal = Decimal("0.0400")
    policy_version: str = "risk-policy/2.0.0"


@dataclass(frozen=True)
class DrawdownTier:
    """Drawdown ≥ threshold applies `multiplier` to allowed risk. A multiplier of
    0 suspends new live trades. `top_tier_only` restricts to CERTIFIED_LIVE."""

    threshold: Decimal
    multiplier: Decimal
    top_tier_only: bool = False


DEFAULT_DRAWDOWN_TIERS: tuple[DrawdownTier, ...] = (
    DrawdownTier(Decimal("0.02"), Decimal("0.75")),
    DrawdownTier(Decimal("0.04"), Decimal("0.40"), top_tier_only=True),
    DrawdownTier(Decimal("0.06"), Decimal("0")),
)


def _dec(value: Any, name: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MandateError(f"{name}: not a decimal: {value!r}") from exc
    if not d.is_finite():
        raise MandateError(f"{name}: must be finite")
    return d


def _fraction(value: Any, name: str) -> Decimal:
    d = _dec(value, name)
    if d <= 0 or d >= 1:
        raise MandateError(f"{name}: must be a fraction in (0, 1), got {d}")
    return d


@dataclass(frozen=True)
class TradingMandate:
    mandate_id: str
    version: str
    account_alias: str
    venue: str
    mode: AuthorizationMode
    instruments: frozenset[str]
    allowed_strategies: frozenset[str]
    max_risk_per_trade: Decimal
    max_open_stop_risk: Decimal
    max_daily_loss: Decimal
    max_weekly_drawdown: Decimal
    max_currency_leg_exposure: Decimal
    max_consecutive_losses: int
    max_positions_per_instrument: int
    max_total_positions: int
    tier1_event_policy: str  # "flat" | "strategy_specific"
    weekend_hold_allowed: bool
    forbidden: frozenset[str]
    owner_signature_ref: str
    signed_at_unix: int
    expires_at_unix: int
    drawdown_tiers: tuple[DrawdownTier, ...] = DEFAULT_DRAWDOWN_TIERS
    #: TRD-ENH-060 — per-strategy live ceilings. Absent means "use
    #: max_risk_per_trade", so an unamended mandate behaves exactly as before.
    #: Only an owner-signed new mandate version can change a value here: this
    #: is the single place in the system where a ceiling can rise.
    strategy_risk_budgets: Mapping[str, Decimal] = field(default_factory=dict)

    def risk_budget_for(self, strategy_id: str) -> Decimal:
        """The live base risk for one strategy.

        Always the *minimum* of the per-strategy budget and the mandate
        ceiling, so a budget can only ever narrow what the mandate already
        allowed — never widen it.
        """
        budget = self.strategy_risk_budgets.get(strategy_id)
        if budget is None:
            return self.max_risk_per_trade
        return min(budget, self.max_risk_per_trade)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        ceilings: PlatformCeilings = PlatformCeilings(),
        authority: "OwnerAuthorityVerifier | None" = None,
    ) -> "TradingMandate":
        required = (
            "mandate_id", "version", "account_alias", "venue", "mode", "instruments",
            "allowed_strategies", "max_risk_per_trade", "max_open_stop_risk",
            "max_daily_loss", "max_weekly_drawdown", "max_currency_leg_exposure",
            "max_consecutive_losses", "max_positions_per_instrument", "max_total_positions",
            "tier1_event_policy", "weekend_hold_allowed", "forbidden",
            "owner_signature_ref", "signed_at_unix", "expires_at_unix",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise MandateError(f"mandate missing fields: {missing}")

        try:
            mode = AuthorizationMode(str(data["mode"]))
        except ValueError as exc:
            raise MandateError(f"invalid mode: {data['mode']!r}") from exc

        # P0-TRADE-001 — "signed" meant "the field is not empty", so any mandate was
        # admissible and only PlatformCeilings bounded what it could then do. The mandate
        # id and version are the subject, so a signature over version 3 does not admit a
        # version 4 that widened the risk limits.
        verifier = authority if authority is not None else OwnerAuthorityVerifier()
        try:
            verified = verifier.verify(
                str(data["owner_signature_ref"]),
                act="mandate-admit",
                subject=f"{data['mandate_id']}:{data['version']}",
                now_unix=int(data.get("signed_at_unix") or time.time()),
                # A mandate is a standing document, re-read on every process start, so it
                # is not a one-shot act. Its replay bound is its own expiry plus the
                # signature covering its version: widening the limits needs a new one.
                single_use=False,
                max_lifetime_seconds=MAX_STANDING_LIFETIME_SECONDS,
            )
        except OwnerAuthorityError as exc:
            raise MandateError(f"mandate is not owner-signed: {exc}") from exc

        forbidden = frozenset(str(x) for x in _as_iterable(data["forbidden"]))
        absent = HARD_FORBIDDEN_BEHAVIOURS - forbidden
        if absent:
            raise MandateError(f"mandate must forbid hard-prohibited behaviours; missing {sorted(absent)}")

        tiers_raw = data.get("drawdown_tiers")
        tiers = DEFAULT_DRAWDOWN_TIERS if tiers_raw is None else _parse_tiers(tiers_raw)

        m = cls(
            mandate_id=str(data["mandate_id"]),
            version=str(data["version"]),
            account_alias=str(data["account_alias"]),
            venue=str(data["venue"]),
            mode=mode,
            instruments=frozenset(str(x).upper() for x in _as_iterable(data["instruments"])),
            allowed_strategies=frozenset(str(x) for x in _as_iterable(data["allowed_strategies"])),
            max_risk_per_trade=_fraction(data["max_risk_per_trade"], "max_risk_per_trade"),
            max_open_stop_risk=_fraction(data["max_open_stop_risk"], "max_open_stop_risk"),
            max_daily_loss=_fraction(data["max_daily_loss"], "max_daily_loss"),
            max_weekly_drawdown=_fraction(data["max_weekly_drawdown"], "max_weekly_drawdown"),
            max_currency_leg_exposure=_fraction(data["max_currency_leg_exposure"], "max_currency_leg_exposure"),
            max_consecutive_losses=int(data["max_consecutive_losses"]),
            max_positions_per_instrument=int(data["max_positions_per_instrument"]),
            max_total_positions=int(data["max_total_positions"]),
            tier1_event_policy=str(data["tier1_event_policy"]),
            weekend_hold_allowed=bool(data["weekend_hold_allowed"]),
            forbidden=forbidden,
            owner_signature_ref=verified.ref,
            signed_at_unix=int(data["signed_at_unix"]),
            expires_at_unix=int(data["expires_at_unix"]),
            drawdown_tiers=tiers,
            strategy_risk_budgets=_parse_budgets(data.get("strategy_risk_budgets")),
        )
        m.validate(ceilings)
        return m

    def _validate_budgets(self, ceilings: PlatformCeilings) -> None:
        for sid, budget in sorted(self.strategy_risk_budgets.items()):
            if budget <= 0:
                raise MandateError(f"strategy_risk_budget for {sid} must be > 0")
            if budget > self.max_risk_per_trade:
                raise MandateError(
                    f"strategy_risk_budget for {sid} ({budget}) exceeds "
                    f"max_risk_per_trade ({self.max_risk_per_trade})")
            if budget > ceilings.max_risk_per_trade:
                raise MandateError(
                    f"strategy_risk_budget for {sid} ({budget}) exceeds the platform ceiling "
                    f"({ceilings.max_risk_per_trade})")
            if sid not in self.allowed_strategies:
                raise MandateError(f"strategy_risk_budget for {sid}, which is not in allowed_strategies")

    def validate(self, ceilings: PlatformCeilings) -> None:
        if self.tier1_event_policy not in ("flat", "strategy_specific"):
            raise MandateError(f"tier1_event_policy must be flat|strategy_specific, got {self.tier1_event_policy!r}")
        if self.max_consecutive_losses < 1 or self.max_positions_per_instrument < 1 or self.max_total_positions < 1:
            raise MandateError("count limits must be >= 1")
        if self.expires_at_unix <= self.signed_at_unix:
            raise MandateError("mandate expires before it is signed")
        if self.max_risk_per_trade > self.max_open_stop_risk:
            raise MandateError("max_risk_per_trade cannot exceed max_open_stop_risk")
        checks = (
            ("max_risk_per_trade", self.max_risk_per_trade, ceilings.max_risk_per_trade),
            ("max_open_stop_risk", self.max_open_stop_risk, ceilings.max_open_stop_risk),
            ("max_daily_loss", self.max_daily_loss, ceilings.max_daily_loss),
            ("max_weekly_drawdown", self.max_weekly_drawdown, ceilings.max_weekly_drawdown),
            ("max_currency_leg_exposure", self.max_currency_leg_exposure, ceilings.max_currency_leg_exposure),
        )
        self._validate_budgets(ceilings)
        for name, value, ceiling in checks:
            if value > ceiling:
                raise MandateError(f"{name}={value} exceeds platform ceiling {ceiling} ({ceilings.policy_version})")
        prev = Decimal("-1")
        for tier in self.drawdown_tiers:
            if tier.threshold <= prev:
                raise MandateError("drawdown tiers must be strictly increasing")
            if tier.multiplier < 0 or tier.multiplier > 1:
                raise MandateError("drawdown tier multiplier must be within [0, 1]")
            prev = tier.threshold
        if not self.drawdown_tiers or self.drawdown_tiers[-1].multiplier != 0:
            raise MandateError("drawdown tiers must end with a suspending tier (multiplier 0)")

    def is_expired(self, now_unix: int) -> bool:
        return now_unix >= self.expires_at_unix

    def sends_orders(self) -> bool:
        return self.mode in ORDER_SENDING_MODES

    def is_live_money(self) -> bool:
        return self.mode in LIVE_MONEY_MODES


def _as_iterable(value: Any) -> Iterable[Any]:
    if isinstance(value, (str, bytes)):
        raise MandateError("expected a list, got a string")
    return list(value)


def _parse_budgets(raw: Any) -> dict[str, Decimal]:
    """Budgets arrive as strings in the signed mandate document."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise MandateError("strategy_risk_budgets must be a mapping")
    return {str(k): _fraction(v, f"strategy_risk_budgets[{k}]") for k, v in raw.items()}


def _parse_tiers(raw: Any) -> tuple[DrawdownTier, ...]:
    tiers = []
    for item in _as_iterable(raw):
        if not isinstance(item, Mapping):
            raise MandateError("drawdown tier must be a mapping")
        tiers.append(
            DrawdownTier(
                threshold=_dec(item["threshold"], "drawdown_tier.threshold"),
                multiplier=_dec(item["multiplier"], "drawdown_tier.multiplier"),
                top_tier_only=bool(item.get("top_tier_only", False)),
            )
        )
    return tuple(tiers)
