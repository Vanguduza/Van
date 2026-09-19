"""Rev 1 §§18, 38 — the Computer Interaction Fabric.

§38 asks for the Browser Fabric generalised, and is precise about what must not
happen along the way: *typed operations only*, and *no unrestricted "do
anything" primitive*. That constraint is the entire value. A fabric that can
reach any application through one generic `execute(command)` has no boundary at
all, however carefully the caller is written.

So an operation is a member of a closed set, each binding a mission, a target
application, an action class, a scope, a checkpoint and a verifier. Adding a new
capability means adding a typed operation and declaring it — not passing a
different string.

Boundary escalation reuses the browser's four states rather than inventing a
parallel vocabulary, and reuses the rule that was hardened there: a payment,
an injection refusal or an A4/A5 request is POLICY_FORBIDDEN and never becomes
an owner prompt, because a prompt the target surface can provoke is a way to
obtain authority rather than a way to supervise it.

P2-CU-001 — what this module did *not* have was an executor. No worker exists for
any of the four surfaces, so `begin` recorded an operation nobody would perform
and the fabric read as a built capability in every matrix that listed it. The
audit's own disposition was "delete or fold"; the closure blueprint's owner
decision 6 said delete, on the description "a stub".

That description was wrong, and reading the code is what corrects it. This is not
a stub: the refusals are real, ordered and tested, and the ledger is durable. What
it lacks is a worker. Deleting a hardened boundary because the thing it bounds has
not been built yet gets the order backwards — the boundary is the part you want
written first, and re-deriving it later under delivery pressure is how a
`RUN_ARBITRARY` appears.

So the module stays and the missing executor becomes an enforced runtime state
instead of a claim in a document. `SURFACE_WORKERS` is empty, `begin` refuses
`OPERATION_NO_WORKER_FOR_SURFACE` before it writes anything, and
`/v1/computer-use/health` says so to the owner. The day a worker lands, it
registers and the refusal stops firing; until then nothing can call this and
believe work will happen.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.browser.models import BrowserBoundaryType
from van_gateway.capability.models import CLASS_RANK
from van_gateway.models import ActionClass
from van_gateway.storage.db import Store


class Surface(str, Enum):
    """Where an operation happens. Each has its own worker and its own limits."""

    BROWSER = "BROWSER"
    DESKTOP = "DESKTOP"
    TERMINAL = "TERMINAL"
    MOBILE = "MOBILE"


class OperationType(str, Enum):
    """§38 — typed operations only. This set is the boundary.

    There is deliberately no RUN_ARBITRARY, EXECUTE or EVAL. Anything a new
    integration needs is a new member here, reviewed as a change to this file,
    rather than a new string passed at runtime.
    """

    NAVIGATE = "NAVIGATE"
    READ = "READ"
    EXTRACT = "EXTRACT"
    CLICK = "CLICK"
    TYPE_TEXT = "TYPE_TEXT"
    FILL_FROM_REFERENCE = "FILL_FROM_REFERENCE"
    SELECT = "SELECT"
    SCROLL = "SCROLL"
    SCREENSHOT = "SCREENSHOT"
    UPLOAD_FROM_REFERENCE = "UPLOAD_FROM_REFERENCE"
    DOWNLOAD_TO_EVIDENCE = "DOWNLOAD_TO_EVIDENCE"
    WAIT_FOR_CONDITION = "WAIT_FOR_CONDITION"

    @property
    def mutates(self) -> bool:
        return self in (
            OperationType.CLICK, OperationType.TYPE_TEXT,
            OperationType.FILL_FROM_REFERENCE, OperationType.SELECT,
            OperationType.UPLOAD_FROM_REFERENCE,
        )

    @property
    def max_action_class(self) -> ActionClass:
        """§38 — the ceiling a typed operation can ever carry.

        A3 for anything that mutates, and never A4: an irreversible or
        send-as-owner effect needs approval bound to the exact action, which is
        by definition not a standing property of an operation type.
        """
        return ActionClass.A3 if self.mutates else ActionClass.A2


class OperationState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    BLOCKED_UNSAFE = "BLOCKED_UNSAFE"


class ComputerUseError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class OperationRequest(BaseModel):
    """Every field is a binding §38 requires; none is optional in spirit."""

    mission_id: str
    surface: Surface
    target_application: str
    operation_type: OperationType
    action_class: ActionClass = ActionClass.A2
    scope: dict[str, Any] = Field(default_factory=dict)
    activity_id: str | None = None
    verifier_type: str = "NONE"


#: Surfaces with a worker that can actually perform an operation.
#:
#: P2-CU-001 — empty, and that is the finding made enforceable rather than hidden.
#: BROWSER is not here either: the browser fabric serves it through its own workers and
#: its own ledger, and routing browser work through a second record would give the owner
#: two accounts of one task, which is the coherence defect P2-COH-001 closed.
SURFACE_WORKERS: frozenset[Surface] = frozenset()


class ComputerInteractionFabric:
    """Typed operations against any surface, bound to a mission and evidenced."""

    def __init__(self, store: Store, *, workers: frozenset[Surface] | None = None) -> None:
        self.store = store
        self.workers = SURFACE_WORKERS if workers is None else workers

    def surfaces(self) -> dict[str, bool]:
        """Which surfaces can be acted on, for the health payload and for tests."""
        return {surface.value: surface in self.workers for surface in Surface}

    async def begin(
        self, request: OperationRequest, *, now_ms: int | None = None
    ) -> str:
        """Refuse before doing, and refuse for a stated reason."""
        # Order matters: the absolute prohibition is reported before the
        # per-type ceiling, so an A4 request is refused as "never on this
        # fabric" rather than as "this operation type caps lower" — which
        # would invite someone to look for an operation type that does not.
        if request.action_class in (ActionClass.A4, ActionClass.A5):
            # §38 / §2.4 — the generic fabric is never an A4 surface, on any
            # surface. This is the browser rule generalised, not relaxed.
            raise ComputerUseError(
                "OPERATION_ACTION_CLASS_PROHIBITED", request.action_class.value
            )
        if CLASS_RANK[request.action_class] > CLASS_RANK[
            request.operation_type.max_action_class
        ]:
            raise ComputerUseError(
                "OPERATION_ABOVE_TYPE_CEILING",
                f"{request.operation_type.value} caps at "
                f"{request.operation_type.max_action_class.value}, "
                f"asked for {request.action_class.value}",
            )
        if request.operation_type.mutates and request.verifier_type == "NONE":
            # §34 — a side effect that cannot prove it happened is not admitted.
            raise ComputerUseError(
                "OPERATION_MUTATION_WITHOUT_VERIFIER", request.operation_type.value
            )
        if not request.target_application.strip():
            raise ComputerUseError("OPERATION_TARGET_REQUIRED")
        if request.surface not in self.workers:
            # P2-CU-001 — last of the refusals on purpose. A policy prohibition must not be
            # reported as a configuration gap: "no worker for DESKTOP" invites someone to
            # start a worker, and an A4 request must never read as one worker away from
            # permitted. It is also *before* the insert, so an operation nobody can perform
            # leaves no row claiming it is PENDING.
            raise ComputerUseError(
                "OPERATION_NO_WORKER_FOR_SURFACE", request.surface.value
            )

        now = int(time.time() * 1000) if now_ms is None else now_ms
        operation_id = f"cop_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO computer_operations(
              operation_id, mission_id, activity_id, surface, target_application,
              operation_type, action_class, scope_json, checkpoint_ref, evidence_ref,
              verifier_type, state, error_code, started_at_ms, completed_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 'PENDING', NULL, ?, NULL)
            """,
            (
                operation_id, request.mission_id, request.activity_id, request.surface.value,
                request.target_application, request.operation_type.value,
                request.action_class.value, Store.dumps(request.scope),
                request.verifier_type, now,
            ),
        )
        return operation_id

    async def checkpoint(
        self, operation_id: str, *, checkpoint_ref: str, now_ms: int | None = None
    ) -> None:
        await self.store.execute(
            "UPDATE computer_operations SET state = 'CHECKPOINTED', checkpoint_ref = ? "
            "WHERE operation_id = ?",
            (checkpoint_ref, operation_id),
        )

    async def complete(
        self,
        operation_id: str,
        *,
        state: OperationState,
        evidence_ref: str | None = None,
        error_code: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """A mutation completes only with evidence. §34, on every surface."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT operation_type FROM computer_operations WHERE operation_id = ?",
            (operation_id,),
        )
        if row is None:
            raise ComputerUseError("OPERATION_UNKNOWN", operation_id)
        op_type = OperationType(str(row["operation_type"]))
        if state is OperationState.COMPLETED and op_type.mutates and not evidence_ref:
            raise ComputerUseError("OPERATION_COMPLETION_REQUIRES_EVIDENCE", operation_id)
        await self.store.execute(
            "UPDATE computer_operations SET state = ?, evidence_ref = ?, error_code = ?, "
            "completed_at_ms = ? WHERE operation_id = ?",
            (state.value, evidence_ref, error_code, now, operation_id),
        )

    @staticmethod
    def classify_boundary(
        *,
        requested_action_class: ActionClass | None = None,
        payment_suspected: bool = False,
        injection_suspected: bool = False,
        within_declared_scope: bool = True,
    ) -> BrowserBoundaryType:
        """§38 — the browser's escalation vocabulary, generalised unchanged.

        Reusing the enum rather than defining a parallel one is deliberate: the
        four states already mean the right things, and a second vocabulary would
        drift from the one that has been hardened.
        """
        if payment_suspected or injection_suspected:
            return BrowserBoundaryType.POLICY_FORBIDDEN
        if requested_action_class in (ActionClass.A4, ActionClass.A5):
            return BrowserBoundaryType.POLICY_FORBIDDEN
        if not within_declared_scope:
            return BrowserBoundaryType.OWNER_EXTENSION_REQUIRED
        return BrowserBoundaryType.BOUNDED_SAFE_EXTENSION

    async def for_mission(self, mission_id: str) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM computer_operations WHERE mission_id = ? ORDER BY started_at_ms",
            (mission_id,),
        )
        out = []
        for row in rows:
            item = dict(row)
            item["scope"] = json.loads(str(item.pop("scope_json")))
            out.append(item)
        return out


__all__ = [
    "SURFACE_WORKERS",
    "ComputerInteractionFabric",
    "ComputerUseError",
    "OperationRequest",
    "OperationState",
    "OperationType",
    "Surface",
]
