"""Versioned trading context compiler (TRD-REV51-093, G3).

Every model invocation is answered against exactly one compiled context, and
this is the only thing that builds one. The packet's hook is "cognitive wake
handler before every model invocation" — meaning nothing may assemble its own
inputs on the side, because a context that is not sealed cannot be replayed
and an assessment whose inputs are unknown is not evidence of anything.

Four properties do the work.

**Versioned per section.** Each section carries the version of the component
that produced it, and the context hash covers those versions. When the world
model changes shape, contexts compiled before and after it hash differently
and are visibly not comparable — which is the honest outcome, and much better
than a silently shifting baseline (INV-REPLAY-001).

**Deterministic.** Sections are ordered by name, values are canonical JSON.
The same inputs give the same hash on any machine at any time.

**Fails closed.** A required section that could not be built raises rather
than compiling a thinner context. A model that answers confidently from a
context missing its risk state is worse than a model that was never called,
and INV-FAIL-001 means the deterministic path carries on regardless.

**Budgeted out loud.** Contexts have a size ceiling, and when it binds the
compiler drops optional sections in a declared order and *records the drops
inside the context it returns*. A context that quietly shrank is a context
whose assessment cannot be compared with yesterday's.

The compiler also refuses credentials outright rather than masking them. A
secret reaching this boundary is a defect upstream, and `****` in a sealed
record would hide it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash, canonical_json

COMPILER_VERSION = "context-compiler/5.1.0"

#: Sections without which an assessment is not worth having. The names are
#: the contract; a caller that cannot fill one must not paper over it.
REQUIRED_SECTIONS: tuple[str, ...] = ("decision_point", "risk_state", "world")

#: Dropped first when the budget binds, in this order. Everything not named
#: here is required and never dropped.
OPTIONAL_DROP_ORDER: tuple[str, ...] = (
    "rejection_history", "calendar", "analogues", "strategy_health", "execution_quality",
)

#: Canonical-JSON bytes. Generous for an offline pipeline, finite on purpose:
#: an unbounded context makes cost and latency a function of uptime.
DEFAULT_BUDGET_BYTES = 262_144

#: Anything whose key looks like this must not be in a context at all.
SECRET_KEY = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|authorization|bearer|session[_-]?id)",
    re.IGNORECASE)


class ContextIncomplete(RuntimeError):
    """A required section is missing or unbuildable. Fail closed."""


class ContextContaminated(RuntimeError):
    """Something that must never be in a context reached the compiler."""


@dataclass(frozen=True)
class ContextSection:
    name: str
    version: str
    payload: Mapping[str, Any]

    def body(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "payload": dict(self.payload)}

    @property
    def size_bytes(self) -> int:
        return len(canonical_json(self.body()).encode("utf-8"))


@dataclass(frozen=True)
class CompiledContext:
    """A sealed, bounded, versioned input to exactly one invocation."""

    sections: tuple[ContextSection, ...]
    compiled_ms: int
    budget_bytes: int
    dropped_sections: tuple[str, ...]
    compiler_version: str = COMPILER_VERSION
    context_hash: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "compiler_version": self.compiler_version,
            "compiled_ms": self.compiled_ms,
            "budget_bytes": self.budget_bytes,
            "dropped_sections": list(self.dropped_sections),
            "sections": [s.body() for s in self.sections],
        }

    def sealed(self) -> "CompiledContext":
        return CompiledContext(**{**self.__dict__, "context_hash": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.context_hash) and self.context_hash == canonical_hash(self.body())

    @property
    def size_bytes(self) -> int:
        return len(canonical_json(self.body()).encode("utf-8"))

    @property
    def is_complete(self) -> bool:
        """No optional section was dropped. A comparison across contexts that
        differ here is comparing two different questions."""
        return not self.dropped_sections

    def section(self, name: str) -> Optional[ContextSection]:
        return next((s for s in self.sections if s.name == name), None)

    def versions(self) -> dict[str, str]:
        return {s.name: s.version for s in self.sections}


def _scan_for_secrets(name: str, node: Any, path: str = "") -> None:
    if isinstance(node, Mapping):
        for k, v in node.items():
            here = f"{path}.{k}" if path else str(k)
            if SECRET_KEY.search(str(k)):
                raise ContextContaminated(
                    f"section {name!r} carries {here!r}; a credential in a context is an "
                    "upstream defect, and masking it here would hide that")
            _scan_for_secrets(name, v, here)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _scan_for_secrets(name, v, f"{path}[{i}]")


class ContextCompiler:
    """Builds one sealed context from registered section producers."""

    def __init__(self, *, budget_bytes: int = DEFAULT_BUDGET_BYTES) -> None:
        self.budget_bytes = budget_bytes
        self._producers: dict[str, tuple[str, Callable[[], Mapping[str, Any]]]] = {}

    def register(self, name: str, version: str,
                 producer: Callable[[], Mapping[str, Any]]) -> None:
        """Register a section. Re-registering replaces, so a service can
        rebuild its wiring without accumulating stale producers."""
        self._producers[name] = (version, producer)

    def compile(self, *, now_ms: int) -> CompiledContext:
        built: dict[str, ContextSection] = {}
        failed: list[str] = []
        for name, (version, producer) in sorted(self._producers.items()):
            try:
                payload = producer()
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {exc}")
                continue
            _scan_for_secrets(name, payload)
            built[name] = ContextSection(name, version, dict(payload))

        missing = [n for n in REQUIRED_SECTIONS if n not in built]
        if missing or any(f.split(":")[0] in REQUIRED_SECTIONS for f in failed):
            raise ContextIncomplete(
                "required sections unavailable: "
                + ", ".join(sorted(missing + [f for f in failed if f.split(':')[0] in REQUIRED_SECTIONS])))

        dropped: list[str] = [f.split(":")[0] for f in failed]
        ctx = self._within_budget(built, dropped, now_ms)
        return ctx

    def _within_budget(self, built: dict[str, ContextSection], dropped: list[str],
                       now_ms: int) -> CompiledContext:
        def assemble() -> CompiledContext:
            return CompiledContext(
                sections=tuple(built[n] for n in sorted(built)),
                compiled_ms=now_ms, budget_bytes=self.budget_bytes,
                dropped_sections=tuple(sorted(set(dropped))),
            ).sealed()

        ctx = assemble()
        for name in OPTIONAL_DROP_ORDER:
            if ctx.size_bytes <= self.budget_bytes:
                break
            if name in built:
                del built[name]
                dropped.append(name)
                ctx = assemble()
        if ctx.size_bytes > self.budget_bytes:
            # Only required sections remain and they still do not fit. Say so
            # rather than truncating one of them into something misleading.
            raise ContextIncomplete(
                f"required sections alone are {ctx.size_bytes} bytes, over the "
                f"{self.budget_bytes}-byte budget")
        return ctx


def compile_decision_context(*, decision_point: Mapping[str, Any],
                             risk_state: Mapping[str, Any],
                             world,
                             now_ms: int,
                             analogues=None,
                             calendar: Optional[Sequence[Mapping[str, Any]]] = None,
                             execution_quality: Optional[Mapping[str, Any]] = None,
                             budget_bytes: int = DEFAULT_BUDGET_BYTES) -> CompiledContext:
    """The standard wiring: one decision point against the projected world.

    `world` is a TradingWorldModel; `analogues` a RetrievalResult from 097.
    Both are optional to construct but the world section is required to exist,
    which is why it is passed rather than looked up.
    """
    from vati.cognition.world_model import WORLD_MODEL_VERSION

    c = ContextCompiler(budget_bytes=budget_bytes)
    c.register("decision_point", "decision-point/5.1.0", lambda: dict(decision_point))
    c.register("risk_state", "risk-state/5.1.0", lambda: dict(risk_state))
    c.register("world", WORLD_MODEL_VERSION, lambda: {
        "events_applied": world.events_applied,
        "kill_switch_triggers": sorted(world.kill_switch_triggers),
        "open_intents": len(world.open_intents),
        "world_digest": world.digest(),
    })
    c.register("strategy_health", WORLD_MODEL_VERSION, lambda: {
        "degrading": world.degrading_strategies(),
        "strategies": {k: v.body() for k, v in sorted(world.strategies.items())},
    })
    c.register("rejection_history", WORLD_MODEL_VERSION, lambda: {
        "top_reasons": [list(t) for t in world.top_rejection_reasons()],
        "recent": [list(r) for r in world.recent_rejections[-50:]],
    })
    if analogues is not None:
        c.register("analogues", analogues.retrieval_version, lambda: analogues.body())
    if calendar is not None:
        c.register("calendar", "calendar-recorder/5.1.0", lambda: {"records": list(calendar)})
    if execution_quality is not None:
        c.register("execution_quality", "execution-policy/1.0.0", lambda: dict(execution_quality))
    return c.compile(now_ms=now_ms)
