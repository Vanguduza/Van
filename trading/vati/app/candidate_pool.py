"""CandidatePool: the bounded window where symbols compete (§14, TRD-ENH-033).

Without a pool there is no moment at which two opportunities coexist, so
allocation has nothing to allocate between. The pool creates that moment and
bounds it: a candidate that has expired, been superseded, or whose source state
is no longer current cannot become a `TradeIntent`.

States are explicit because the owner surface has to distinguish "we chose
something else" from "the Risk Authority refused it" from "it went stale while
we waited". Those are different facts and a single `rejected` hides all three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Iterator, Optional

from vati.arbiter.candidate import CandidateOpportunity


class CandidateState(str, Enum):
    ACTIVE = "ACTIVE"
    SELECTED = "SELECTED"
    DEFERRED = "DEFERRED"
    #: The allocator ranked it below the winner.
    NOT_SELECTED = "NOT_SELECTED"
    #: The Risk Authority refused it. Not the allocator's decision.
    RISK_REJECTED = "RISK_REJECTED"
    #: The router refused it (kill switch, venue, protection).
    ROUTER_REFUSED = "ROUTER_REFUSED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


#: States from which a candidate may still become an intent.
ELIGIBLE_STATES = frozenset({CandidateState.ACTIVE, CandidateState.DEFERRED})


@dataclass
class PooledCandidate:
    candidate: CandidateOpportunity
    state: CandidateState = CandidateState.ACTIVE
    reason: str = ""
    updated_at_ms: int = 0

    @property
    def candidate_id(self) -> str:
        return self.candidate.candidate_id


class CandidatePool:
    """Per-account. Deterministic ordering; no hidden iteration order."""

    def __init__(self, *, account_alias: str) -> None:
        self.account_alias = account_alias
        self._rows: dict[str, PooledCandidate] = {}

    # -- ingestion ---------------------------------------------------------

    def admit(self, candidate: CandidateOpportunity, *, now_ms: int) -> PooledCandidate:
        if candidate.account_alias != self.account_alias:
            raise ValueError(
                f"candidate for {candidate.account_alias} offered to {self.account_alias} pool")
        # A newer candidate for the same setup replaces the older one rather
        # than competing against it — otherwise one setup gets several votes.
        key = candidate.supersession_key
        for row in self._rows.values():
            if (row.state in ELIGIBLE_STATES
                    and row.candidate.supersession_key == key
                    and row.candidate.generated_at_ms < candidate.generated_at_ms):
                row.state = CandidateState.SUPERSEDED
                row.reason = f"superseded by {candidate.candidate_id}"
                row.updated_at_ms = now_ms
        row = PooledCandidate(candidate=candidate, updated_at_ms=now_ms)
        self._rows[candidate.candidate_id] = row
        return row

    def admit_all(self, candidates: Iterable[CandidateOpportunity], *, now_ms: int) -> None:
        for c in sorted(candidates, key=lambda c: (c.generated_at_ms, c.candidate_id)):
            self.admit(c, now_ms=now_ms)

    # -- lifecycle ---------------------------------------------------------

    def expire_stale(self, *, now_ms: int) -> tuple[str, ...]:
        """Expire anything past its TTL. Called before every allocation pass."""
        expired: list[str] = []
        for row in self._rows.values():
            if row.state in ELIGIBLE_STATES and not row.candidate.fresh_at(now_ms):
                row.state = CandidateState.EXPIRED
                row.reason = f"ttl elapsed at {row.candidate.valid_until_ms}"
                row.updated_at_ms = now_ms
                expired.append(row.candidate_id)
        return tuple(expired)

    def mark(self, candidate_id: str, state: CandidateState, *, reason: str, now_ms: int) -> None:
        row = self._rows.get(candidate_id)
        if row is None:
            raise KeyError(candidate_id)
        row.state = state
        row.reason = reason
        row.updated_at_ms = now_ms

    # -- reads -------------------------------------------------------------

    def active(self, *, now_ms: int) -> tuple[CandidateOpportunity, ...]:
        """Fresh, eligible candidates in deterministic order."""
        rows = [r for r in self._rows.values()
                if r.state in ELIGIBLE_STATES and r.candidate.fresh_at(now_ms)]
        rows.sort(key=lambda r: (r.candidate.symbol, r.candidate.strategy_id, r.candidate_id))
        return tuple(r.candidate for r in rows)

    def row(self, candidate_id: str) -> Optional[PooledCandidate]:
        return self._rows.get(candidate_id)

    def rows(self) -> tuple[PooledCandidate, ...]:
        return tuple(sorted(self._rows.values(), key=lambda r: r.candidate_id))

    def by_state(self, state: CandidateState) -> tuple[PooledCandidate, ...]:
        return tuple(r for r in self.rows() if r.state is state)

    def symbols(self, *, now_ms: int) -> tuple[str, ...]:
        return tuple(sorted({c.symbol for c in self.active(now_ms=now_ms)}))

    def prune(self, *, now_ms: int, keep_ms: int = 24 * 3_600_000) -> int:
        """Drop terminal rows older than `keep_ms`, so the pool stays bounded."""
        drop = [cid for cid, r in self._rows.items()
                if r.state not in ELIGIBLE_STATES and now_ms - r.updated_at_ms > keep_ms]
        for cid in drop:
            del self._rows[cid]
        return len(drop)

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[PooledCandidate]:
        return iter(self.rows())


__all__ = ["ELIGIBLE_STATES", "CandidatePool", "CandidateState", "PooledCandidate"]
