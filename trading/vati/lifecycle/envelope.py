"""PositionRiskEnvelope and released-risk haircut (TRD-REV51-107, G7).

The tempting arithmetic in any scaling system is: "this family has banked
0.8R, so risking another 0.8R is free". It is not free, and INV-PPC-001 is the
rule that says so — ProtectedProfitCredit is zero unless guaranteed exit
capability is *independently certified*.

The reasoning is worth keeping next to the code. Banked profit is only a
buffer if it survives the event that would consume it, and the events that
consume buffers are gaps, halts and venue outages — precisely the conditions
in which an ordinary stop does not execute at its price. A venue-guaranteed
stop, or an owner-confirmed exit already resting at the venue, is different in
kind: someone other than us has undertaken to fill it. So credit requires a
certificate, the certificate has an expiry, and an expired certificate gives
zero credit rather than its last known value.

Everything else here is bookkeeping done at the family level, because that is
the level at which the exposure is real: open risk is net quantity against the
family's current stop, not the sum of its members' notions of their own stops.

The envelope answers three questions and refuses to answer a fourth. It says
what is at stake, what has been banked, and what would be lost in the worst
admissible case. It does not say how much more may be risked — that is the
Risk Authority's, and the envelope is one of its inputs (INV-AUTH-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.lifecycle.family import FamilyState, PositionFamily
from vati.risk.contracts import Direction

PRODUCER = "vati-risk-envelope"
ENVELOPE_VERSION = "risk-envelope/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: Even with certified guaranteed exit, only part of banked profit counts.
#: Guaranteed at the venue is not guaranteed against the venue: counterparty
#: and settlement risk remain ours.
MAX_PROTECTED_PROFIT_FRACTION = Decimal("0.50")


class HaircutReason(str, Enum):
    """Why credit was withheld. Every path to zero is named."""

    NONE = "NONE"
    NO_CERTIFICATE = "NO_CERTIFICATE"
    CERTIFICATE_EXPIRED = "CERTIFICATE_EXPIRED"
    CERTIFICATE_NOT_INDEPENDENT = "CERTIFICATE_NOT_INDEPENDENT"
    FAMILY_DIVERGED = "FAMILY_DIVERGED"
    NO_REALISED_PROFIT = "NO_REALISED_PROFIT"
    STOP_UNKNOWN = "STOP_UNKNOWN"


@dataclass(frozen=True)
class GuaranteedExitCertificate:
    """Independent evidence that an exit will fill at a known price.

    `issuer` is the party that undertook to fill it. `self_asserted` exists so
    a certificate VAN wrote about its own intentions is visibly not
    independent evidence (INV-EVID-001) rather than quietly counting.
    """

    certificate_id: str
    family_id: str
    issuer: str
    guaranteed_price: Decimal
    issued_ms: int
    expires_ms: int
    self_asserted: bool = False

    def valid_at(self, now_ms: int) -> bool:
        return not self.self_asserted and self.issued_ms <= now_ms < self.expires_ms

    def body(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id, "family_id": self.family_id,
            "issuer": self.issuer, "guaranteed_price": str(self.guaranteed_price),
            "issued_ms": self.issued_ms, "expires_ms": self.expires_ms,
            "self_asserted": self.self_asserted,
        }


@dataclass(frozen=True)
class PositionRiskEnvelope:
    """What one family has at stake, banked, and would lose at its worst."""

    family_id: str
    account_alias: str
    symbol: str
    net_quantity: Decimal
    average_entry: Optional[Decimal]
    current_stop: Optional[Decimal]
    mark: Decimal
    value_per_price_unit: Decimal
    open_risk_money: Decimal
    realised_money: Decimal
    unrealised_money: Decimal
    protected_profit_credit: Decimal
    haircut_reason: HaircutReason
    equity: Decimal
    assessed_ms: int
    envelope_version: str = ENVELOPE_VERSION

    @property
    def worst_case_loss(self) -> Decimal:
        """Loss if the family stops out now, after any certified credit.

        Credit reduces the number only when it was earned by a certificate,
        which is the whole content of INV-PPC-001.
        """
        loss = self.open_risk_money - self.protected_profit_credit
        return loss if loss > ZERO else ZERO

    @property
    def open_risk_pct(self) -> Optional[Decimal]:
        if self.equity <= ZERO:
            return None
        return self.open_risk_money / self.equity

    @property
    def worst_case_pct(self) -> Optional[Decimal]:
        if self.equity <= ZERO:
            return None
        return self.worst_case_loss / self.equity

    @property
    def risk_is_known(self) -> bool:
        """A family whose stop is unknown has unbounded risk, not zero risk."""
        return self.current_stop is not None

    def body(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "account_alias": self.account_alias,
            "symbol": self.symbol,
            "net_quantity": str(self.net_quantity),
            "average_entry": None if self.average_entry is None else str(self.average_entry),
            "current_stop": None if self.current_stop is None else str(self.current_stop),
            "mark": str(self.mark),
            "open_risk_money": str(self.open_risk_money),
            "realised_money": str(self.realised_money),
            "unrealised_money": str(self.unrealised_money),
            "protected_profit_credit": str(self.protected_profit_credit),
            "haircut_reason": self.haircut_reason.value,
            "worst_case_loss": str(self.worst_case_loss),
            "open_risk_pct": None if self.open_risk_pct is None else str(self.open_risk_pct),
            "worst_case_pct": None if self.worst_case_pct is None else str(self.worst_case_pct),
            "risk_is_known": self.risk_is_known,
            "assessed_ms": self.assessed_ms,
            "envelope_version": self.envelope_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class EnvelopeCalculator:
    """Computes envelopes, and decides what banked profit is allowed to mean."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._certificates: dict[str, GuaranteedExitCertificate] = {}

    def certify(self, cert: GuaranteedExitCertificate) -> GuaranteedExitCertificate:
        self._certificates[cert.family_id] = cert
        return cert

    def certificate(self, family_id: str) -> Optional[GuaranteedExitCertificate]:
        return self._certificates.get(family_id)

    def _credit(self, family: PositionFamily, realised: Decimal,
                now_ms: int) -> tuple[Decimal, HaircutReason]:
        """INV-PPC-001, in one place, with every path to zero named."""
        if realised <= ZERO:
            return ZERO, HaircutReason.NO_REALISED_PROFIT
        if family.state is FamilyState.DIVERGED:
            return ZERO, HaircutReason.FAMILY_DIVERGED
        cert = self._certificates.get(family.family_id)
        if cert is None:
            return ZERO, HaircutReason.NO_CERTIFICATE
        if cert.self_asserted:
            return ZERO, HaircutReason.CERTIFICATE_NOT_INDEPENDENT
        if not cert.valid_at(now_ms):
            # An expired certificate gives zero, not its last known value.
            return ZERO, HaircutReason.CERTIFICATE_EXPIRED
        return realised * MAX_PROTECTED_PROFIT_FRACTION, HaircutReason.NONE

    def compute(self, family: PositionFamily, *, mark: Decimal,
                value_per_price_unit: Decimal, equity: Decimal,
                now_ms: int) -> PositionRiskEnvelope:
        mark = dec(mark)
        vpu = dec(value_per_price_unit)
        realised = family.realised_money * vpu
        unrealised = family.unrealised_money(mark) * vpu

        if family.current_stop is None:
            # Unknown stop is unbounded risk. Using the mark-to-zero distance
            # would be arbitrary, so the envelope says the risk is not known
            # and the caller must treat that as blocking, not as small.
            open_risk = ZERO
            credit, reason = ZERO, HaircutReason.STOP_UNKNOWN
        else:
            distance = abs(mark - family.current_stop)
            if family.direction is Direction.LONG and family.current_stop > mark:
                distance = ZERO      # stop already through the mark; exit is due
            if family.direction is Direction.SHORT and family.current_stop < mark:
                distance = ZERO
            open_risk = distance * family.net_quantity * vpu
            credit, reason = self._credit(family, realised, now_ms)

        env = PositionRiskEnvelope(
            family_id=family.family_id, account_alias=family.account_alias,
            symbol=family.symbol, net_quantity=family.net_quantity,
            average_entry=family.average_entry, current_stop=family.current_stop,
            mark=mark, value_per_price_unit=vpu, open_risk_money=open_risk,
            realised_money=realised, unrealised_money=unrealised,
            protected_profit_credit=credit, haircut_reason=reason,
            equity=dec(equity), assessed_ms=now_ms)

        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.POSITION_RISK_ENVELOPE, self._producer, env.body(),
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=family.family_id))
        return env

    def portfolio_worst_case(self, envelopes: list[PositionRiskEnvelope]) -> dict[str, Any]:
        """Sum of family worst cases. Families with unknown risk are named
        rather than counted as zero."""
        unknown = [e.family_id for e in envelopes if not e.risk_is_known]
        total = sum((e.worst_case_loss for e in envelopes if e.risk_is_known), ZERO)
        return {
            "envelope_version": ENVELOPE_VERSION,
            "families": len(envelopes),
            "worst_case_loss": str(total),
            "credited": str(sum((e.protected_profit_credit for e in envelopes), ZERO)),
            "families_with_unknown_risk": unknown,
            "risk_fully_known": not unknown,
        }
