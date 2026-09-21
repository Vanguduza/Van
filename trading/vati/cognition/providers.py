"""Trading model provider registry and quota scheduler (TRD-REV51-091, G2).

Four models sit behind one interface: Fable 5.1, then GPT-6 Astra, then Claude
Opus 5, then GPT-5.6 Sol. INV-MODEL-001 says that order is *availability
routing* and that a fallback may never relax controls. That sentence is easy
to write and easy to violate by accident, because the obvious way to build a
fallback chain is to let each provider carry its own settings — and then the
cheap provider quietly gets a looser leash.

So the registry refuses to store per-provider controls at all. Every provider
must declare the same `control_profile` string, and one that declares a
different value is rejected at registration rather than at the point of use.
What a provider may differ in is *availability*: quota, concurrency, latency
budget, cost. Nothing that touches what the result is allowed to mean.

Quota is a fixed window counter rather than a leaky bucket. The scheduler is
called from replayable pipelines, so "how many calls had we made by time T"
must have exactly one answer; a bucket that drains continuously gives a
different answer depending on when you ask.

Exhaustion is not an error. `acquire` returning None is the normal way the
system says "no cognition this cycle", and the caller answers it with
`contracts.abstention(...)` — a sealed record that the deterministic path
stood alone (INV-FAIL-001, INV-EVID-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional

from vati.cognition.contracts import ModelRole

#: The one control profile. Every provider must declare it; the string exists
#: so that "the fallback uses the same controls" is a checkable fact.
CONTROL_PROFILE = "vati-controls/5.1.0"

#: The declared hierarchy, primary first. A registry that does not match this
#: shape is refused: the order is part of the invariant, not configuration.
HIERARCHY: tuple[ModelRole, ...] = (
    ModelRole.PRIMARY,
    ModelRole.FIRST_FALLBACK,
    ModelRole.SECOND_FALLBACK,
    ModelRole.FINAL_FALLBACK,
)

#: Consecutive failures before a provider is rested. Low, because the next
#: provider has identical authority — there is nothing to lose by moving on.
FAILURE_COOLDOWN_THRESHOLD = 3


class RegistryError(ValueError):
    """The provider registry would not hold the invariant."""


class ProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AT_CONCURRENCY = "AT_CONCURRENCY"
    COOLING_DOWN = "COOLING_DOWN"       # recent consecutive failures
    DISABLED = "DISABLED"                # owner or operator decision


@dataclass(frozen=True)
class ModelProvider:
    """One model's availability terms. Deliberately carries no control terms."""

    model_id: str
    role: ModelRole
    max_requests_per_window: int
    window_ms: int
    max_concurrent: int = 1
    latency_budget_ms: int = 60_000
    cost_per_request_micros: int = 0
    cooldown_ms: int = 300_000
    control_profile: str = CONTROL_PROFILE

    def validate(self) -> None:
        if self.control_profile != CONTROL_PROFILE:
            raise RegistryError(
                f"{self.model_id} declares control profile {self.control_profile!r}; "
                f"INV-MODEL-001 requires every provider to run {CONTROL_PROFILE!r}")
        if self.role not in HIERARCHY:
            raise RegistryError(f"{self.model_id} has role {self.role.value}, which is not in the hierarchy")
        if self.max_requests_per_window <= 0 or self.window_ms <= 0:
            raise RegistryError(f"{self.model_id} has an empty quota window")
        if self.max_concurrent <= 0:
            raise RegistryError(f"{self.model_id} allows no concurrency")


@dataclass
class _Usage:
    window_start_ms: int = 0
    used: int = 0
    in_flight: int = 0
    consecutive_failures: int = 0
    cooldown_until_ms: int = 0
    disabled: bool = False
    total_requests: int = 0
    total_failures: int = 0
    total_cost_micros: int = 0


@dataclass(frozen=True)
class ProviderLease:
    """Permission to make exactly one invocation against one provider."""

    lease_id: str
    model_id: str
    role: ModelRole
    control_profile: str
    acquired_ms: int
    deadline_ms: int
    attempt: int              # 1 for the primary, 2 for the first fallback, ...

    @property
    def is_fallback(self) -> bool:
        return self.role is not ModelRole.PRIMARY


class ProviderRegistry:
    """The four providers, in hierarchy order, with identical authority."""

    def __init__(self, providers: Optional[list[ModelProvider]] = None) -> None:
        self._by_role: dict[ModelRole, ModelProvider] = {}
        for p in providers or ():
            self.register(p)

    def register(self, provider: ModelProvider) -> ModelProvider:
        provider.validate()
        if provider.role in self._by_role:
            raise RegistryError(
                f"role {provider.role.value} is already held by "
                f"{self._by_role[provider.role].model_id}; the hierarchy has one model per rung")
        if any(p.model_id == provider.model_id for p in self._by_role.values()):
            raise RegistryError(f"{provider.model_id} is already registered")
        self._by_role[provider.role] = provider
        return provider

    def ordered(self) -> list[ModelProvider]:
        return [self._by_role[r] for r in HIERARCHY if r in self._by_role]

    def get(self, role: ModelRole) -> Optional[ModelProvider]:
        return self._by_role.get(role)

    def by_model_id(self, model_id: str) -> Optional[ModelProvider]:
        return next((p for p in self._by_role.values() if p.model_id == model_id), None)

    def validate_complete(self) -> None:
        """Every rung filled. Used at service startup, not at each call."""
        missing = [r.value for r in HIERARCHY if r not in self._by_role]
        if missing:
            raise RegistryError(f"hierarchy is incomplete: {', '.join(missing)}")

    def __len__(self) -> int:
        return len(self._by_role)

    def __iter__(self) -> Iterator[ModelProvider]:
        return iter(self.ordered())


class QuotaScheduler:
    """Picks the highest provider that is available right now.

    'Available' means within its fixed quota window, below its concurrency
    limit, not resting after consecutive failures, and not disabled. It never
    means 'cheapest' or 'most capable' — capability is not a scheduling input,
    because a decision that depends on which model answered would make the
    fallback chain behaviourally visible, which is precisely what INV-MODEL-001
    forbids.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry
        self._usage: dict[str, _Usage] = {p.model_id: _Usage() for p in registry}
        self._seq = 0

    # ------------------------------------------------------------------ state
    def _roll_window(self, p: ModelProvider, u: _Usage, now_ms: int) -> None:
        if now_ms - u.window_start_ms >= p.window_ms:
            u.window_start_ms = now_ms - (now_ms % p.window_ms) if p.window_ms else now_ms
            u.used = 0

    def state(self, model_id: str, now_ms: int) -> ProviderState:
        p = self.registry.by_model_id(model_id)
        if p is None:
            raise KeyError(model_id)
        u = self._usage[model_id]
        self._roll_window(p, u, now_ms)
        if u.disabled:
            return ProviderState.DISABLED
        if now_ms < u.cooldown_until_ms:
            return ProviderState.COOLING_DOWN
        if u.in_flight >= p.max_concurrent:
            return ProviderState.AT_CONCURRENCY
        if u.used >= p.max_requests_per_window:
            return ProviderState.QUOTA_EXHAUSTED
        return ProviderState.AVAILABLE

    def disable(self, model_id: str, *, disabled: bool = True) -> None:
        self._usage[model_id].disabled = disabled

    # ---------------------------------------------------------------- acquire
    def acquire(self, *, now_ms: int, exclude_model_ids: tuple[str, ...] = ()) -> Optional[ProviderLease]:
        """The next usable rung, or None when every rung is unavailable.

        ``exclude_model_ids`` is request-local fallback state. It lets an orchestration
        layer move to the next provider after one provider fails without mutating the
        provider's global enabled/disabled state. The registry still owns hierarchy order.

        None is an ordinary outcome, not an exception: the caller records an
        abstention and the deterministic path proceeds untouched.
        """
        excluded = frozenset(exclude_model_ids)
        for attempt, p in enumerate(self.registry.ordered(), start=1):
            if p.model_id in excluded:
                continue
            if self.state(p.model_id, now_ms) is not ProviderState.AVAILABLE:
                continue
            u = self._usage[p.model_id]
            u.used += 1
            u.in_flight += 1
            u.total_requests += 1
            u.total_cost_micros += p.cost_per_request_micros
            self._seq += 1
            return ProviderLease(
                lease_id=f"lease-{now_ms}-{self._seq}",
                model_id=p.model_id,
                role=p.role,
                control_profile=p.control_profile,   # always CONTROL_PROFILE
                acquired_ms=now_ms,
                deadline_ms=now_ms + p.latency_budget_ms,
                attempt=attempt,
            )
        return None

    def release(self, lease: ProviderLease, *, ok: bool, now_ms: int) -> None:
        u = self._usage[lease.model_id]
        p = self.registry.by_model_id(lease.model_id)
        assert p is not None
        u.in_flight = max(0, u.in_flight - 1)
        timed_out = now_ms > lease.deadline_ms
        if ok and not timed_out:
            u.consecutive_failures = 0
            return
        u.total_failures += 1
        u.consecutive_failures += 1
        if u.consecutive_failures >= FAILURE_COOLDOWN_THRESHOLD:
            u.cooldown_until_ms = now_ms + p.cooldown_ms
            u.consecutive_failures = 0

    # ----------------------------------------------------------------- report
    def snapshot(self, *, now_ms: int) -> dict:
        return {
            "control_profile": CONTROL_PROFILE,
            "providers": [
                {
                    "model_id": p.model_id,
                    "role": p.role.value,
                    "state": self.state(p.model_id, now_ms).value,
                    "used_in_window": self._usage[p.model_id].used,
                    "quota": p.max_requests_per_window,
                    "in_flight": self._usage[p.model_id].in_flight,
                    "total_requests": self._usage[p.model_id].total_requests,
                    "total_failures": self._usage[p.model_id].total_failures,
                    "total_cost_micros": self._usage[p.model_id].total_cost_micros,
                }
                for p in self.registry
            ],
        }


def default_registry() -> ProviderRegistry:
    """The Rev 5.1 hierarchy with conservative offline quotas.

    The numbers are starting points, not measured optima, and they are here as
    named values so they can be argued with. They are sized for offline
    evolution and shadow measurement, which run on a schedule — not for a
    per-tick path, which cognition is not on.
    """
    return ProviderRegistry([
        ModelProvider("fable-5.1", ModelRole.PRIMARY,
                      max_requests_per_window=120, window_ms=3_600_000,
                      max_concurrent=2, latency_budget_ms=120_000),
        ModelProvider("gpt-6-astra", ModelRole.FIRST_FALLBACK,
                      max_requests_per_window=120, window_ms=3_600_000,
                      max_concurrent=2, latency_budget_ms=120_000),
        ModelProvider("claude-opus-5", ModelRole.SECOND_FALLBACK,
                      max_requests_per_window=120, window_ms=3_600_000,
                      max_concurrent=2, latency_budget_ms=120_000),
        ModelProvider("gpt-5.6-sol", ModelRole.FINAL_FALLBACK,
                      max_requests_per_window=120, window_ms=3_600_000,
                      max_concurrent=2, latency_budget_ms=120_000),
    ])
