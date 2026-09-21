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


@dataclass
class ProtectionManager:
    rules: dict[str, _Rule] = field(default_factory=dict)

    def register(self, position_id: str, *, symbol: str, direction: Direction, entry: Decimal, stop: Decimal, target: Optional[Decimal], opened_ms: int,
                 time_stop_ms: Optional[int] = None, break_even_trigger: Optional[Decimal] = None, trail_distance: Optional[Decimal] = None, software_stop: bool = False) -> None:
        if direction is Direction.LONG and not stop < entry or direction is Direction.SHORT and not stop > entry:
            raise ProtectionError("stop on wrong side of entry")
        self.rules[position_id] = _Rule(symbol, direction, entry, stop, target, opened_ms, time_stop_ms, break_even_trigger, trail_distance, software_stop)

    def stop_of(self, position_id: str) -> Decimal:
        return self.rules[position_id].stop

    def tighten(self, position_id: str, new_stop: Decimal) -> None:
        r = self.rules[position_id]
        if (r.direction is Direction.LONG and new_stop < r.stop) or (r.direction is Direction.SHORT and new_stop > r.stop):
            raise ProtectionError("widening a protective stop is forbidden (A5 widen_protective_stop)")
        r.stop = new_stop

    def on_mark(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExitInstruction]:
        out: list[ExitInstruction] = []
        for pid, r in list(self.rules.items()):
            if r.symbol != symbol:
                continue
            px_exit = bid if r.direction is Direction.LONG else ask
            fav = (px_exit - r.entry) if r.direction is Direction.LONG else (r.entry - px_exit)
            r.mfe, r.mae = max(r.mfe, fav), min(r.mae, fav)
            # software stop / target
            if (r.direction is Direction.LONG and px_exit <= r.stop) or (r.direction is Direction.SHORT and px_exit >= r.stop):
                out.append(ExitInstruction(pid, "CLOSE", "SOFTWARE_STOP" if r.software_stop else "STRUCTURE", px_exit)); del self.rules[pid]; continue
            if r.target is not None and ((r.direction is Direction.LONG and px_exit >= r.target) or (r.direction is Direction.SHORT and px_exit <= r.target)):
                out.append(ExitInstruction(pid, "CLOSE", "TARGET", px_exit)); del self.rules[pid]; continue
            if r.time_stop_ms is not None and now_ms >= r.time_stop_ms:
                out.append(ExitInstruction(pid, "CLOSE", "TIME_STOP", px_exit)); del self.rules[pid]; continue
            # break-even (only tightens)
            if r.break_even_trigger is not None and not r.be_done and fav >= r.break_even_trigger:
                new = r.entry
                if (r.direction is Direction.LONG and new > r.stop) or (r.direction is Direction.SHORT and new < r.stop):
                    r.stop = new; r.be_done = True; out.append(ExitInstruction(pid, "MODIFY_STOP", "BREAK_EVEN", new))
            # trailing (only tightens)
            if r.trail_distance is not None and fav > r.trail_distance:
                new = (px_exit - r.trail_distance) if r.direction is Direction.LONG else (px_exit + r.trail_distance)
                if (r.direction is Direction.LONG and new > r.stop) or (r.direction is Direction.SHORT and new < r.stop):
                    r.stop = new; out.append(ExitInstruction(pid, "MODIFY_STOP", "TRAIL", new))
        return out

    def forget(self, position_id: str) -> None:
        self.rules.pop(position_id, None)
