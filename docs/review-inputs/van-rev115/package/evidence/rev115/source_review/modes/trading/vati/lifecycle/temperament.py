"""Conservative temperament-aware winner management within existing capsule policy.

An owner profile may alter *how much* profit is banked on an already-permitted
PARTIAL_TAKE action. It cannot create an action, enable ADD/pyramiding, weaken
invalidated-thesis exits or change any protective stop. All venue operations
continue through the existing Risk Authority and Execution Router.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from vati.lifecycle.scale_policy import AdjustmentPolicy
from vati.risk.mandate import TradingTemperament

EXIT_TEMPERAMENT_POLICY_VERSION = "temperament-exit/1.0.0"

# Reduce early profit-taking to leave a larger winner running, but only
# if the existing capsule policy already permits PARTIAL_TAKE.
MAX_PARTIAL_TAKE = {
    TradingTemperament.RISKY: Decimal("0.25"),
    TradingTemperament.AGGRESSIVE: Decimal("0.15"),
}


def profit_pursuit_policy(
    existing: AdjustmentPolicy,
    temperament: TradingTemperament | None,
) -> AdjustmentPolicy:
    """Narrow a permitted action's partial quantity; never grant a new one.

    NORMAL and legacy use the capsule's original policy untouched.
    RISKY and AGGRESSIVE reduce only the fraction of a qualified partial
    exit. Weak/invalidation actions still follow the ordinary engine's
    high-priority REDUCE / EXIT branches.
    """
    if temperament not in MAX_PARTIAL_TAKE:
        return existing
    limit = MAX_PARTIAL_TAKE[temperament]
    new_fraction = min(existing.partial_take_fraction, limit)
    if new_fraction == existing.partial_take_fraction:
        return existing
    return replace(existing, policy_id=existing.policy_id + "/" + temperament.value,
                   partial_take_fraction=new_fraction)


__all__ = ["EXIT_TEMPERAMENT_POLICY_VERSION", "profit_pursuit_policy"]
