"""MarketDataDisagreementDetector (§31, TRD-ENH-075).

A broker's feed is the one VATI executes against, so a stale or bad quote there
is a decision made on fiction. Where an independent reference exists, disagreement
is detectable.

The rule that keeps this honest: **never assume the reference is correct merely
because it is independent.** Disagreement means "one of these is wrong and I do
not know which", so the response is fail-safe — wait, reduce or halt — never
"switch to the other feed".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from vati.core.canonical import canonical_hash

ZERO = Decimal("0")

AGREE = "AGREE"
MINOR_DIVERGENCE = "MINOR_DIVERGENCE"
MAJOR_DIVERGENCE = "MAJOR_DIVERGENCE"
EXECUTION_FEED_STALE = "EXECUTION_FEED_STALE"
REFERENCE_FEED_STALE = "REFERENCE_FEED_STALE"
BOTH_STALE = "BOTH_STALE"
SPREAD_ANOMALY = "SPREAD_ANOMALY"
NO_REFERENCE = "NO_REFERENCE"

#: Fail-safe responses. Note what is absent: there is no SWITCH_FEED.
CONTINUE = "CONTINUE"
WAIT = "WAIT"
REDUCE = "REDUCE"
HALT = "HALT"


@dataclass(frozen=True)
class FeedSample:
    source: str
    bid: Decimal
    ask: Decimal
    as_of_ms: int

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True)
class DisagreementObservation:
    symbol: str
    as_of_ms: int
    state: str
    response: str
    execution_age_ms: int
    reference_age_ms: Optional[int]
    relative_divergence: Optional[Decimal]
    spread_ratio: Optional[Decimal]
    reasons: tuple[str, ...] = ()
    observation_hash: str = ""

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if k != "observation_hash"} | {
            "reasons": list(self.reasons)}

    def sealed(self) -> "DisagreementObservation":
        return DisagreementObservation(
            **{**self.__dict__, "observation_hash": canonical_hash(self.as_dict())})


class MarketDataDisagreementDetector:
    def __init__(
        self,
        *,
        max_age_ms: int = 5_000,
        minor_divergence: Decimal = Decimal("0.0005"),
        major_divergence: Decimal = Decimal("0.0020"),
        spread_anomaly_ratio: Decimal = Decimal("4"),
    ) -> None:
        self.max_age_ms = max_age_ms
        self.minor_divergence = minor_divergence
        self.major_divergence = major_divergence
        self.spread_anomaly_ratio = spread_anomaly_ratio

    def compare(
        self,
        *,
        symbol: str,
        execution: FeedSample,
        reference: Optional[FeedSample],
        now_ms: int,
    ) -> DisagreementObservation:
        reasons: list[str] = []
        exec_age = now_ms - execution.as_of_ms
        ref_age = (now_ms - reference.as_of_ms) if reference else None

        exec_stale = exec_age > self.max_age_ms
        ref_stale = ref_age is not None and ref_age > self.max_age_ms

        if reference is None:
            # No reference is not agreement; it is absence of evidence.
            state = EXECUTION_FEED_STALE if exec_stale else NO_REFERENCE
            response = HALT if exec_stale else CONTINUE
            if exec_stale:
                reasons.append(f"execution_age:{exec_age}ms")
            return DisagreementObservation(symbol, now_ms, state, response, exec_age, None,
                                           None, None, tuple(reasons)).sealed()

        divergence = None
        if reference.mid > ZERO:
            divergence = abs(execution.mid - reference.mid) / reference.mid
        spread_ratio = None
        if reference.spread > ZERO:
            spread_ratio = execution.spread / reference.spread

        if exec_stale and ref_stale:
            state, response = BOTH_STALE, HALT
            reasons.append(f"both_stale:{exec_age}/{ref_age}")
        elif exec_stale:
            state, response = EXECUTION_FEED_STALE, HALT
            reasons.append(f"execution_age:{exec_age}ms")
        elif ref_stale:
            # The reference being stale says nothing about the execution feed.
            state, response = REFERENCE_FEED_STALE, WAIT
            reasons.append(f"reference_age:{ref_age}ms")
        elif divergence is not None and divergence >= self.major_divergence:
            state, response = MAJOR_DIVERGENCE, HALT
            reasons.append(f"divergence:{divergence}")
        elif spread_ratio is not None and spread_ratio >= self.spread_anomaly_ratio:
            state, response = SPREAD_ANOMALY, REDUCE
            reasons.append(f"spread_ratio:{spread_ratio}")
        elif divergence is not None and divergence >= self.minor_divergence:
            state, response = MINOR_DIVERGENCE, REDUCE
            reasons.append(f"divergence:{divergence}")
        else:
            state, response = AGREE, CONTINUE

        return DisagreementObservation(symbol, now_ms, state, response, exec_age, ref_age,
                                       divergence, spread_ratio, tuple(reasons)).sealed()


__all__ = [
    "AGREE", "BOTH_STALE", "CONTINUE", "EXECUTION_FEED_STALE", "HALT",
    "MAJOR_DIVERGENCE", "MINOR_DIVERGENCE", "NO_REFERENCE", "REDUCE",
    "REFERENCE_FEED_STALE", "SPREAD_ANOMALY", "WAIT",
    "DisagreementObservation", "FeedSample", "MarketDataDisagreementDetector",
]
