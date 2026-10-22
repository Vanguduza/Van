"""Recoverable risk lockouts (P1-TRADE-RISK-005).

Two account rules became permanent once they fired, which no autonomous system can
recover from by itself:

* **Losing streak.** `consecutive_losses` reset only on a win. At the limit no trade
  was allowed, so no win could come, and the strategy stopped for good — until a
  process restart silently reset the in-memory counter to zero.
* **Drawdown tier.** At 4% from the high-water mark only `CERTIFIED_LIVE` strategies
  could trade. With none certified, nothing traded, equity could not recover, and the
  restriction never lifted. A restart re-baselined the peak, silently.

This module replaces both with rules that bound loss, recover on their own where it is
safe, escalate to the owner where it is not, and never reset silently:

Losing streak, per strategy and across the account (two scopes):
  1. At `max_consecutive_losses` losses in a row the scope enters a COOLDOWN
     (default 24 h). Other strategies keep trading.
  2. After the cooldown the scope is on PROBATION: it trades at reduced risk
     (default ×0.5) until it records a win, which ends probation.
  3. More than `max_cooldowns_per_week` cooldowns inside 7 days SUSPENDS the scope.
     Only an owner-signed `loss-streak-reset` clears a suspension.
  4. State is a fold over the ledger (TRADE_REVIEW outcomes and reset events), so a
     restart rebuilds it exactly.

Drawdown:
  * "Top tier only" means the highest promotion state actually present among the
    strategies the mandate allows (`relative_top_state`), so a demo account keeps
    trading its best strategies at the tier's reduced size and can recover.
  * The suspending tier still stops autonomous trading. Only an owner-signed
    `drawdown-resume` re-baselines the high-water mark.
  * The high-water mark is restored from the ledger on start, never re-baselined by it.

Manual (owner-initiated) trades, strategy `owner.manual` (blueprint §7.4.2), have their
own scope with the same cooldown, probation and suspension: a manual losing streak
pauses manual entries only (no revenge trading), never an autonomous strategy, and an
autonomous cooldown never blocks the owner. Nothing here admits a manual order; that
is the manual-trading packet (DU-28).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional

from vati.risk.contracts import StrategyState
from vati.risk.history_scope import risk_history_for_account, RiskHistoryScopeError

ZERO, ONE = Decimal("0"), Decimal("1")
ACCOUNT_SCOPE = "*ACCOUNT*"
HOUR_MS = 3_600_000
WEEK_MS = 7 * 24 * HOUR_MS

#: The mandate strategy of owner-initiated trades (blueprint §7.4.2).
MANUAL_STRATEGY_ID = "owner.manual"

PROMOTION_ORDER = (
    StrategyState.RESEARCH, StrategyState.BACKTEST, StrategyState.VALIDATION, StrategyState.DEMO,
    StrategyState.SHADOW, StrategyState.LIMITED_LIVE, StrategyState.CERTIFIED_LIVE,
)

RESET_EVENT = "LOSS_STREAK_RESET"
COOLDOWN_EVENT = "LOSS_STREAK_COOLDOWN"
SUSPEND_EVENT = "LOSS_STREAK_SUSPENDED"
DRAWDOWN_RESUME_EVENT = "DRAWDOWN_RESUMED"


@dataclass(frozen=True)
class LockoutPolicy:
    max_consecutive_losses: int
    cooldown_ms: int = 24 * HOUR_MS
    probation_risk_multiplier: Decimal = Decimal("0.5")
    max_cooldowns_per_week: int = 2


@dataclass
class _Scope:
    losses: int = 0
    cooldown_until_ms: int = 0
    probation: bool = False
    suspended: bool = False
    cooldowns: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class StreakVerdict:
    lock: str                    # "" when the scope may trade
    risk_multiplier: Decimal     # ≤ 1; probation reduces it
    losses: int                  # current streak of the strategy scope (informational)


def is_manual(strategy_id: str) -> bool:
    return strategy_id == MANUAL_STRATEGY_ID or strategy_id.startswith(MANUAL_STRATEGY_ID + ".")


def _scopes(strategy_id: str) -> tuple[str, ...]:
    """A manual trade counts only in its own scope; an autonomous one also in the account's."""
    return (strategy_id,) if is_manual(strategy_id) else (strategy_id, ACCOUNT_SCOPE)


class LossStreakGovernor:
    def __init__(self, policy: LockoutPolicy) -> None:
        self.policy = policy
        self._scopes: dict[str, _Scope] = {}
        self.recovery_issue = ""

    def _scope(self, key: str) -> _Scope:
        return self._scopes.setdefault(key, _Scope())

    # ----------------------------------------------------------------- events
    def on_close(self, strategy_id: str, pnl: Decimal, now_ms: int) -> list[dict]:
        """Record one closed trade. Returns lockout events to log."""
        out: list[dict] = []
        for key in _scopes(strategy_id):
            s = self._scope(key)
            if pnl > ZERO:
                s.losses, s.probation = 0, False
            elif pnl < ZERO:
                s.losses += 1
                if s.losses >= self.policy.max_consecutive_losses and not s.suspended:
                    s.losses = 0
                    s.cooldowns = [t for t in s.cooldowns if now_ms - t < WEEK_MS] + [now_ms]
                    if len(s.cooldowns) > self.policy.max_cooldowns_per_week:
                        s.suspended = True
                        out.append({"event": SUSPEND_EVENT, "scope": key, "cooldowns_this_week": len(s.cooldowns)})
                    else:
                        s.cooldown_until_ms = now_ms + self.policy.cooldown_ms
                        s.probation = True
                        out.append({"event": COOLDOWN_EVENT, "scope": key, "until_ms": s.cooldown_until_ms})
        return out

    def reset(self, scope: str) -> dict:
        """Apply an owner-verified reset (the caller verifies the signature)."""
        self._scopes[scope] = _Scope()
        return {"event": RESET_EVENT, "scope": scope}

    # ---------------------------------------------------------------- verdict
    def verdict(self, strategy_id: str, now_ms: int) -> StreakVerdict:
        if self.recovery_issue:
            own = self._scopes.get(strategy_id)
            return StreakVerdict(self.recovery_issue, ZERO, own.losses if own else 0)
        mult = ONE
        for key in _scopes(strategy_id):
            s = self._scopes.get(key)
            if s is None:
                continue
            if s.suspended:
                return StreakVerdict(f"{key} suspended after repeated losing streaks; owner reset required", ZERO, s.losses)
            if now_ms < s.cooldown_until_ms:
                return StreakVerdict(f"{key} cooling down after {self.policy.max_consecutive_losses} losses until {s.cooldown_until_ms}", ZERO, s.losses)
            if s.probation:
                mult = min(mult, self.policy.probation_risk_multiplier)
        own = self._scopes.get(strategy_id)
        return StreakVerdict("", mult, own.losses if own else 0)

    # ---------------------------------------------------------------- rebuild
    @classmethod
    def rebuild(cls, policy: LockoutPolicy, events: Iterable, *, account_alias: str | None = None) -> "LossStreakGovernor":
        """Fold TRADE_REVIEW outcomes and owner resets, in ledger order."""
        g = cls(policy)
        if account_alias is not None:
            history = risk_history_for_account(events, account_alias)
            events = history.events
            g.recovery_issue = history.issue
        for ev in events:
            kind = getattr(ev.kind, "value", ev.kind)
            if kind == "TRADE_REVIEW":
                sid, pnl = ev.payload.get("strategy_id"), ev.payload.get("pnl")
                if sid and pnl is not None:
                    g.on_close(sid, Decimal(str(pnl)), ev.event_time_ms)
            elif kind == "SESSION" and ev.payload.get("event") == RESET_EVENT:
                g.reset(ev.payload["scope"])
        return g


def restore_peak_equity(events: Iterable, *, account_alias: str | None = None) -> Optional[Decimal]:
    """The high-water mark the account last decided against, or an owner re-baseline.

    Read from RISK_DECISION inputs (every decision records its snapshot) and
    DRAWDOWN_RESUMED events, in ledger order; the latest wins. None if the ledger
    has neither.
    """
    peak: Optional[Decimal] = None
    if account_alias is not None:
        history = risk_history_for_account(events, account_alias)
        if history.issue:
            raise RiskHistoryScopeError(history.issue)
        events = history.events
    for ev in events:
        kind = getattr(ev.kind, "value", ev.kind)
        if kind == "RISK_DECISION":
            snap = (ev.payload.get("inputs") or {}).get("snapshot") or {}
            if snap.get("peak_equity") is not None:
                peak = Decimal(str(snap["peak_equity"]))
        elif kind == "SESSION" and ev.payload.get("event") == DRAWDOWN_RESUME_EVENT:
            peak = Decimal(str(ev.payload["new_peak_equity"]))
    return peak


def restore_equity_baselines(events: Iterable, now_ms: int, *, account_alias: str | None = None) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """(peak, day_start, week_start) to resume with after a restart.

    The peak is always restored (see `restore_peak_equity`). The day and week
    baselines are restored only when the last recorded decision falls in the same
    UTC day / week as `now_ms`; otherwise a new period legitimately starts fresh.
    A restart must not reset the daily-loss or weekly-drawdown limit mid-period.
    """
    peak = day = week = None
    last_ms = None
    if account_alias is not None:
        history = risk_history_for_account(events, account_alias)
        if history.issue:
            raise RiskHistoryScopeError(history.issue)
        events = history.events
    events = list(events)
    peak = restore_peak_equity(events)
    for ev in events:
        if getattr(ev.kind, "value", ev.kind) == "RISK_DECISION":
            snap = (ev.payload.get("inputs") or {}).get("snapshot") or {}
            if snap.get("day_start_equity") is not None:
                day, week, last_ms = Decimal(str(snap["day_start_equity"])), Decimal(str(snap["week_start_equity"])), ev.event_time_ms
    if last_ms is None:
        return peak, None, None
    same_day = last_ms // 86_400_000 == now_ms // 86_400_000
    same_week = (last_ms // 86_400_000) // 7 == (now_ms // 86_400_000) // 7
    return peak, (day if same_day else None), (week if same_week else None)


def relative_top_state(states: Iterable[StrategyState]) -> Optional[StrategyState]:
    """Highest promotion state among `states`; None when none is on the ladder."""
    ranked = [s for s in states if s in PROMOTION_ORDER]
    return max(ranked, key=PROMOTION_ORDER.index) if ranked else None


def at_or_above(state: StrategyState, floor: StrategyState) -> bool:
    return state in PROMOTION_ORDER and PROMOTION_ORDER.index(state) >= PROMOTION_ORDER.index(floor)


__all__ = [
    "ACCOUNT_SCOPE", "COOLDOWN_EVENT", "DRAWDOWN_RESUME_EVENT", "MANUAL_STRATEGY_ID", "LockoutPolicy", "LossStreakGovernor",
    "RESET_EVENT", "SUSPEND_EVENT", "StreakVerdict", "at_or_above", "is_manual", "relative_top_state",
    "restore_peak_equity",
]
