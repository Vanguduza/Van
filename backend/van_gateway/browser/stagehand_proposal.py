"""Owner decision 2026-09-29 §8 — Stagehand proposes; the Browser Harness executes.

Stagehand's ``observe()`` returns candidate actions (``selector``, ``method``, ``arguments``,
``description``) without performing them. This module turns one such candidate into a typed
Harness operation, or refuses it. It never calls Stagehand ``act()``.

What the Harness can perform on a Stagehand-observed selector without Stagehand:

* ``click``/``tap``  -> ``click(selector)``
* ``press``/``keypress`` -> ``press(key)`` (the key is ``arguments[0]``)
* ``scroll``/``scrollIntoView`` -> ``scroll``

``fill``/``type`` and every other method are refused: they carry literal text, and the
Harness only fills ``secretref://`` references resolved inside the worker (§407). Refusing is
the honest result; replaying them through Stagehand would give it actuation authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

STAGEHAND_METHODS: dict[str, str] = {
    "click": "click",
    "tap": "click",
    "press": "press_key",
    "keypress": "press_key",
    "scroll": "scroll",
    "scrollintoview": "scroll",
}


class SemanticProposalRefused(RuntimeError):
    """Stagehand observed something the Harness will not perform on its behalf."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TypedStagehandAction:
    operation: str
    selector: str | None
    key: str | None
    description: str | None
    observed: dict[str, Any]


def typed_action_from_stagehand(
    candidate: Any, *, allowed_operations: Iterable[str] | None = None
) -> TypedStagehandAction:
    if not isinstance(candidate, dict):
        raise SemanticProposalRefused("CANDIDATE_NOT_OBJECT")
    method = str(candidate.get("method") or "").strip().lower()
    operation = STAGEHAND_METHODS.get(method)
    if operation is None:
        raise SemanticProposalRefused(f"METHOD_NOT_HARNESS_EXECUTABLE:{method[:32] or 'none'}")
    if allowed_operations is not None and operation not in set(allowed_operations):
        raise SemanticProposalRefused(f"OPERATION_NOT_IN_STEP_SET:{operation}")
    selector = candidate.get("selector")
    selector = selector if isinstance(selector, str) and selector else None
    key = None
    if operation == "press_key":
        args = candidate.get("arguments") or []
        key = str(args[0]) if isinstance(args, list) and args and args[0] else None
        if not key:
            raise SemanticProposalRefused("KEY_MISSING")
    if operation != "scroll" and selector is None:
        raise SemanticProposalRefused("SELECTOR_MISSING")
    description = str(candidate.get("description") or "")[:2000] or None
    return TypedStagehandAction(
        operation=operation, selector=selector, key=key, description=description,
        observed=dict(candidate),
    )


__all__ = [
    "STAGEHAND_METHODS",
    "SemanticProposalRefused",
    "TypedStagehandAction",
    "typed_action_from_stagehand",
]
