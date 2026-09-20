"""Exit protection (Rev 2 §28). Stops only tighten. Break-even and trailing
moves are computed deterministically from marks; time stops and targets are
exit instructions; widening a protective stop raises."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.risk.contracts import Direction

ZERO = Decimal("0")


class ProtectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExitInstruction:
    position_id: str
    action: str           # CLOSE | MODIFY_STOP
    reason: str           # SOFTWARE_STOP | TARGET | TIME_STOP | TRAIL | BREAK_EVEN | STRUCTURE
    price: Optional[Decimal] = None
    previous_stop: Optional[Decimal] = None


@dataclass
class _Rule:
    symbol: str
    direction: Direction
    entry: Decimal
    stop: Decimal
    target: Optional[Decimal]
    opened_ms: int
    time_stop_ms: Optional[int]
    break_even_trigger: Optional[Decimal]   # move in price units to trigger BE
    trail_distance: Optional[Decimal]
    software_stop: bool
    mfe: Decimal = ZERO
    mae: Decimal = ZERO
    be_done: bool = False
    pending_close: bool = False


@dataclass
class ProtectionManager:
    rules: dict[str, _Rule] = field(default_factory=dict)

    def register(self, position_id: str, *, symbol: str, direction: Direction, entry: Decimal, stop: Decimal, target: Optional[Decimal], opened_ms: int,
                 time_stop_ms: Optional[int] = None, break_even_trigger: Optional[Decimal] = None, trail_distance: Optional[Decimal] = None, software_stop: bool = False) -> None:
        if direction is Direction.LONG and not stop < entry or direction is Direction.SHORT and not stop > entry:
            raise ProtectionError("stop on wrong side of entry")
        self.rules[position_id] = _Rule(symbol, direction, entry, stop, target, opened_ms, time_stop_ms, break_even_trigger, trail_distance, software_stop)

    def restore(
        self,
        position_id: str,
        *,
        symbol: str,
        direction: Direction,
        entry: Decimal,
        initial_stop: Decimal,
        current_stop: Decimal,
        target: Optional[Decimal],
        opened_ms: int,
        time_stop_ms: Optional[int] = None,
        break_even_trigger: Optional[Decimal] = None,
        trail_distance: Optional[Decimal] = None,
        software_stop: bool = False,
    ) -> None:
        """Reconstruct a rule after restart without permitting a widened stop.

        The original order command supplies the initial stop. The venue, or
        persisted software-stop contract, supplies the current stop. Recovery
        validates the original rule and then applies the current stop through
        the ordinary tighten-only operation.
        """
        self.register(
            position_id, symbol=symbol, direction=direction, entry=entry,
            stop=initial_stop, target=target, opened_ms=opened_ms,
            time_stop_ms=time_stop_ms, break_even_trigger=break_even_trigger,
            trail_distance=trail_distance, software_stop=software_stop,
        )
        self.tighten(position_id, current_stop)
        rule = self.rules[position_id]
        rule.be_done = (
            direction is Direction.LONG and current_stop >= entry
            or direction is Direction.SHORT and current_stop <= entry
        )

    def stop_of(self, position_id: str) -> Decimal:
        return self.rules[position_id].stop

    def is_software(self, position_id: str) -> bool:
        return self.rules[position_id].software_stop

    def is_close_pending(self, position_id: str) -> bool:
        return self.rules[position_id].pending_close

    def tighten(self, position_id: str, new_stop: Decimal) -> None:
        r = self.rules[position_id]
        if (r.direction is Direction.LONG and new_stop < r.stop) or (r.direction is Direction.SHORT and new_stop > r.stop):
            raise ProtectionError("widening a protective stop is forbidden (A5 widen_protective_stop)")
        r.stop = new_stop

    def close_confirmed(self, position_id: str) -> None:
        self.rules.pop(position_id, None)

    def close_failed(self, position_id: str) -> None:
        rule = self.rules.get(position_id)
        if rule is not None:
            rule.pending_close = False

    def rollback_unconfirmed_tighten(
        self,
        position_id: str,
        *,
        previous_stop: Decimal,
        attempted_stop: Decimal,
    ) -> None:
        """Restore local truth when the venue rejected a proposed tighter stop.

        This is not a protective-stop widening at the venue: the venue never
        accepted the attempted stop. It merely rolls the in-memory mirror back
        to the still-active venue stop.
        """
        rule = self.rules.get(position_id)
        if rule is None:
            return
        if rule.stop != attempted_stop:
            raise ProtectionError("cannot rollback a stop that has changed since submission")
        rule.stop = previous_stop
        rule.be_done = (
            rule.direction is Direction.LONG and previous_stop >= rule.entry
            or rule.direction is Direction.SHORT and previous_stop <= rule.entry
        )

    def on_mark(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExitInstruction]:
        out: list[ExitInstruction] = []
        for pid, r in list(self.rules.items()):
            if r.symbol != symbol:
                continue
            px_exit = bid if r.direction is Direction.LONG else ask
            fav = (px_exit - r.entry) if r.direction is Direction.LONG else (r.entry - px_exit)
            r.mfe, r.mae = max(r.mfe, fav), min(r.mae, fav)
            if r.pending_close:
                continue
            # A close request becomes pending. The protection rule is retained
            # until an actual fill/owner confirmation proves the position closed.
            if (r.direction is Direction.LONG and px_exit <= r.stop) or (r.direction is Direction.SHORT and px_exit >= r.stop):
                r.pending_close = True
                out.append(ExitInstruction(pid, "CLOSE", "SOFTWARE_STOP" if r.software_stop else "STRUCTURE", px_exit))
                continue
            if r.target is not None and ((r.direction is Direction.LONG and px_exit >= r.target) or (r.direction is Direction.SHORT and px_exit <= r.target)):
                r.pending_close = True
                out.append(ExitInstruction(pid, "CLOSE", "TARGET", px_exit))
                continue
            if r.time_stop_ms is not None and now_ms >= r.time_stop_ms:
                r.pending_close = True
                out.append(ExitInstruction(pid, "CLOSE", "TIME_STOP", px_exit))
                continue
            # break-even (only tightens)
            if r.break_even_trigger is not None and not r.be_done and fav >= r.break_even_trigger:
                new = r.entry
                if (r.direction is Direction.LONG and new > r.stop) or (r.direction is Direction.SHORT and new < r.stop):
                    old = r.stop
                    r.stop = new
                    r.be_done = True
                    out.append(ExitInstruction(pid, "MODIFY_STOP", "BREAK_EVEN", new, old))
            # trailing (only tightens)
            if r.trail_distance is not None and fav > r.trail_distance:
                new = (px_exit - r.trail_distance) if r.direction is Direction.LONG else (px_exit + r.trail_distance)
                if (r.direction is Direction.LONG and new > r.stop) or (r.direction is Direction.SHORT and new < r.stop):
                    old = r.stop
                    r.stop = new
                    out.append(ExitInstruction(pid, "MODIFY_STOP", "TRAIL", new, old))
        return out

    def forget(self, position_id: str) -> None:
        self.rules.pop(position_id, None)
