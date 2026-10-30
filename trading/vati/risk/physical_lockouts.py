"""Physical-account loss attribution without widening logical owner controls.

Callers must bind original outcome/control ownership before folding. This
governor neither authenticates a control nor supplies entry authority. Runtime
wiring must retain native provenance, policy, funding and execution gates.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from vati.risk.lockouts import (
    LossStreakGovernor, LockoutPolicy, _Scope, _scopes as scopes_for,
    WEEK_MS, COOLDOWN_EVENT, SUSPEND_EVENT, RESET_EVENT,
)


def _alias(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError('physical risk history requires original account alias')
    return value


@dataclass
class _LossGroup:
    at_ms: int
    remaining_owners: set[str]
    probation: bool = False
    countable: bool = True
    cooldown_until_ms: int = 0


@dataclass
class _Attribution:
    pending: list[str] = field(default_factory=list)
    groups: list[_LossGroup] = field(default_factory=list)
    suspension_owners: set[str] = field(default_factory=set)


class PhysicalLossStreakGovernor(LossStreakGovernor):
    """Joint loss clocks whose releases retain each original alias's scope.

    One alias behaves exactly like the existing governor. Mixed loss groups
    remain protective until all their contributing aliases have independently
    reset their own contribution, or the normal clock/profit rules allow it.
    An alias reset cannot erase another alias's pending losses, cooldown,
    probation or suspension. Manual scopes keep their existing separation.
    """

    def __init__(self, policy: LockoutPolicy, *, account_alias: str):
        super().__init__(policy)
        self.account_alias = _alias(account_alias)
        self._attribution: dict[str, _Attribution] = {}

    def _sync(self, key):
        facts = self._attribution[key]
        # Keep the original typed/UI state shape. Attribution stays internal.
        self._scopes[key] = _Scope(
            losses=len(facts.pending),
            cooldown_until_ms=max((g.cooldown_until_ms for g in facts.groups), default=0),
            probation=any(g.probation for g in facts.groups),
            suspended=bool(facts.suspension_owners),
            cooldowns=[g.at_ms for g in facts.groups if g.countable],
        )

    def on_close(self, strategy_id: str, pnl: Decimal, now_ms: int, *,
                 origin_alias: str | None = None, profit_final: bool = False):
        origin = _alias(self.account_alias if origin_alias is None else origin_alias)
        if not isinstance(pnl, Decimal) or not pnl.is_finite():
            raise ValueError('physical risk history requires finite exact outcome')
        if type(now_ms) is not int or now_ms < 0:
            raise ValueError('physical risk history requires original outcome clock')
        out = []
        for key in scopes_for(strategy_id):
            facts = self._attribution.setdefault(key, _Attribution())
            if pnl > 0 and profit_final is True:
                facts.pending.clear()
                for group in facts.groups:
                    group.probation = False
            elif pnl < 0:
                facts.pending.append(origin)
                if len(facts.pending) >= self.policy.max_consecutive_losses and not facts.suspension_owners:
                    for group in facts.groups:
                        if now_ms - group.at_ms >= WEEK_MS:
                            group.countable = False
                    group = _LossGroup(now_ms, set(facts.pending))
                    facts.pending.clear()
                    facts.groups.append(group)
                    count = sum(g.countable for g in facts.groups)
                    if count > self.policy.max_cooldowns_per_week:
                        facts.suspension_owners = set().union(
                            *(g.remaining_owners for g in facts.groups if g.countable))
                        out.append({'event': SUSPEND_EVENT, 'scope': key,
                                    'cooldowns_this_week': count})
                    else:
                        group.cooldown_until_ms = now_ms + self.policy.cooldown_ms
                        group.probation = True
                        out.append({'event': COOLDOWN_EVENT, 'scope': key,
                                    'until_ms': group.cooldown_until_ms})
            self._sync(key)
        return out

    def reset(self, scope: str):
        """Apply only the current actor's already-verified logical reset."""
        self._reset_original_alias(scope, self.account_alias)
        return {'event': RESET_EVENT, 'scope': scope}

    def _reset_original_alias(self, scope, origin_alias):
        """Internal replay boundary; caller must verify the original control."""
        origin = _alias(origin_alias)
        facts = self._attribution.setdefault(scope, _Attribution())
        facts.pending = [a for a in facts.pending if a != origin]
        facts.suspension_owners.discard(origin)
        for group in facts.groups:
            group.remaining_owners.discard(origin)
        facts.groups = [g for g in facts.groups if g.remaining_owners]
        self._sync(scope)

    def original_contributors(self, scope):
        """Read-only attribution for exact owner review; never a reset grant."""
        facts = self._attribution.get(scope)
        if facts is None:
            return ()
        return tuple(sorted(set(facts.pending) | facts.suspension_owners |
            set().union(*(g.remaining_owners for g in facts.groups))))

    @classmethod
    def rebuild(cls, policy, ledger, *, account_alias, native_context, available_at_ms):
        """Fold only independently joined original native financial facts."""
        from vati.risk.physical_history import physical_financial_history
        from vati.execution.review import economic_outcome_final
        if native_context.account_alias != account_alias:
            raise ValueError('physical recovery context differs from its current actor')
        history = physical_financial_history(ledger, native_context, available_at_ms=available_at_ms)
        g = cls(policy, account_alias=account_alias)
        g.native_account_context = native_context
        g.recovery_issue = history.issue
        for fact in history.facts:
            p = fact.payload
            if fact.kind == 'TRADE_REVIEW':
                g.on_close(p['strategy_id'], Decimal(str(p['pnl'])), fact.event_time_ms,
                    origin_alias=fact.origin_alias,
                    profit_final=economic_outcome_final(p.get('maturity'), p.get('pnl_basis')))
            elif fact.kind == 'SESSION' and p['event'] == RESET_EVENT:
                g._reset_original_alias(p['scope'], fact.origin_alias)
        return g
