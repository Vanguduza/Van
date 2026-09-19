"""Rev 1 §§79-85, 24-25, 40 — external reality, evolution, benchmarks, eval.

§22 states the reason these are separate from the owner model, and it is the
single most important structural point in the cognitive-symbiosis half of the
blueprint:

    Owner model:      "How the owner thinks/operates."
    External reality: "What available evidence says now."
    This separation is mandatory to prevent personalization becoming an echo
    chamber.

So `ExternalRealityModel` never reads the owner model and never writes to it.
When they disagree, that disagreement is recorded as a fact about the world —
`contradicts_owner_belief` — and handed to the reasoning kernel to reconcile in
the open, rather than being quietly resolved in favour of whoever VAN knows
better.

The radar's discipline is §23's: **do not auto-adopt.** The pipeline exists to
make adoption slow and evidenced, and `ADMITTED` is unreachable without both a
VAN-specific benchmark and an owner decision reference. §25 adds the same rule
for strategies — promotion requires eval evidence, and there is no
self-modifying path to it.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.capability.models import CLASS_RANK
from van_gateway.models import ActionClass
from van_gateway.storage.db import Store

HARNESS_VERSION = "van-eval-harness-1"


# ------------------------------------------------------- §79 external reality


class ExternalRealityModel:
    """What the evidence says, kept apart from what the owner believes."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def observe(
        self,
        *,
        subject: str,
        claim: str,
        source_kind: str,
        source_ref: str,
        confidence: float = 0.5,
        contradicts_owner_belief: bool = False,
        now_ms: int | None = None,
    ) -> str:
        if not source_ref:
            # §41 — an observation about the world with no source is not an
            # observation, it is an opinion wearing one's clothes.
            raise ValueError("external_observation_requires_source")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        observation_id = f"ext_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO external_reality(
              observation_id, subject, claim, source_kind, source_ref, observed_at_ms,
              confidence, superseded_by, contradicts_owner_belief
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                observation_id, subject, claim, source_kind, source_ref, now, confidence,
                1 if contradicts_owner_belief else 0,
            ),
        )
        return observation_id

    async def current(self, subject: str) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM external_reality WHERE subject = ? AND superseded_by IS NULL "
            "ORDER BY observed_at_ms DESC",
            (subject,),
        )
        return [dict(r) for r in rows]

    async def contradictions(self) -> list[dict[str, Any]]:
        """Where the world disagrees with the owner — for the kernel, not for VAN
        to settle quietly."""
        rows = await self.store.fetchall(
            "SELECT * FROM external_reality WHERE contradicts_owner_belief = 1 "
            "AND superseded_by IS NULL ORDER BY observed_at_ms DESC"
        )
        return [dict(r) for r in rows]


# ------------------------------------------------------ §§80-82 evolution radar


class PipelineState(str, Enum):
    """§81's ladder. Adoption is slow on purpose."""

    DISCOVERED = "DISCOVERED"
    WATCH = "WATCH"
    BENCHMARK = "BENCHMARK"
    SHADOW = "SHADOW"
    PROPOSED = "PROPOSED"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    DEPRECATED = "DEPRECATED"


_FORWARD = {
    PipelineState.DISCOVERED: {PipelineState.WATCH, PipelineState.REJECTED},
    PipelineState.WATCH: {PipelineState.BENCHMARK, PipelineState.REJECTED,
                          PipelineState.DEPRECATED},
    PipelineState.BENCHMARK: {PipelineState.SHADOW, PipelineState.REJECTED,
                              PipelineState.DEPRECATED},
    PipelineState.SHADOW: {PipelineState.PROPOSED, PipelineState.REJECTED,
                           PipelineState.DEPRECATED},
    PipelineState.PROPOSED: {PipelineState.ADMITTED, PipelineState.REJECTED},
    PipelineState.ADMITTED: {PipelineState.SUPERSEDED, PipelineState.DEPRECATED},
    PipelineState.REJECTED: set(),
    PipelineState.SUPERSEDED: set(),
    PipelineState.DEPRECATED: set(),
}


class RadarError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class TechnologyCapabilityRecord(BaseModel):
    """§82 — everything an adoption decision needs, in one row."""

    technology_id: str
    name: str
    category: str
    version: str | None = None
    source: str | None = None
    licence: str | None = None
    security_profile: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    integration_cost: str | None = None
    migration_risk: str | None = None
    owner_value: str | None = None
    pipeline_state: PipelineState = PipelineState.DISCOVERED
    benchmark_digest: str | None = None
    owner_decision_ref: str | None = None
    last_evaluated_at_ms: int | None = None

    @property
    def admissible(self) -> bool:
        """§23 — no adoption without a VAN benchmark and a security review.

        Both, not either. A technology can be fast and still be something VAN
        should not run; it can be safe and still be worse at VAN's actual tasks.
        """
        return bool(self.benchmark_digest) and bool(self.security_profile) and bool(
            self.licence
        )


class AIEvolutionRadar:
    """§80 — track everything, adopt nothing automatically."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def discover(
        self, *, name: str, category: str, source: str | None = None,
        now_ms: int | None = None,
    ) -> TechnologyCapabilityRecord:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        technology_id = f"tech_{name.strip().lower().replace(' ', '_')}"
        existing = await self.get(technology_id)
        if existing is not None:
            return existing
        await self.store.execute(
            """
            INSERT INTO technology_capabilities(
              technology_id, name, category, version, source, licence, security_profile,
              strengths_json, weaknesses_json, integration_cost, migration_risk, owner_value,
              pipeline_state, benchmark_digest, owner_decision_ref, last_evaluated_at_ms,
              created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, NULL, ?, NULL, NULL, '[]', '[]', NULL, NULL, NULL,
                      'DISCOVERED', NULL, NULL, NULL, ?, ?)
            """,
            (technology_id, name, category, source, now, now),
        )
        return await self.get(technology_id)  # type: ignore[return-value]

    async def update(
        self, technology_id: str, *, now_ms: int | None = None, **fields: Any
    ) -> TechnologyCapabilityRecord:
        record = await self.get(technology_id)
        if record is None:
            raise RadarError("TECHNOLOGY_UNKNOWN", technology_id)
        now = int(time.time() * 1000) if now_ms is None else now_ms
        allowed = {
            "version", "source", "licence", "security_profile", "integration_cost",
            "migration_risk", "owner_value", "benchmark_digest",
        }
        for key, value in fields.items():
            if key in allowed:
                await self.store.execute(
                    f"UPDATE technology_capabilities SET {key} = ?, updated_at_ms = ? "
                    "WHERE technology_id = ?",
                    (value, now, technology_id),
                )
            elif key in ("strengths", "weaknesses"):
                await self.store.execute(
                    f"UPDATE technology_capabilities SET {key}_json = ?, updated_at_ms = ? "
                    "WHERE technology_id = ?",
                    (Store.dumps(list(value)), now, technology_id),
                )
        return await self.get(technology_id)  # type: ignore[return-value]

    async def transition(
        self,
        technology_id: str,
        *,
        target: PipelineState,
        owner_decision_ref: str | None = None,
        now_ms: int | None = None,
    ) -> TechnologyCapabilityRecord:
        """§23 — ADMITTED needs a benchmark, a security profile and the owner.

        The three requirements are separate because they fail separately: a
        technology can be benchmarked and unreviewed, reviewed and unbenchmarked,
        or both and still not something the owner wants running.
        """
        record = await self.get(technology_id)
        if record is None:
            raise RadarError("TECHNOLOGY_UNKNOWN", technology_id)
        if target not in _FORWARD[record.pipeline_state]:
            raise RadarError(
                "TECHNOLOGY_ILLEGAL_TRANSITION",
                f"{record.pipeline_state.value}->{target.value}",
            )
        if target is PipelineState.ADMITTED:
            if not record.admissible:
                raise RadarError(
                    "TECHNOLOGY_NOT_ADMISSIBLE",
                    "needs benchmark_digest, security_profile and licence",
                )
            if not owner_decision_ref:
                # §45.14 — the radar attempting direct adoption without approval.
                raise RadarError("TECHNOLOGY_ADOPTION_REQUIRES_OWNER_DECISION", technology_id)
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE technology_capabilities SET pipeline_state = ?, "
            "owner_decision_ref = COALESCE(?, owner_decision_ref), "
            "last_evaluated_at_ms = ?, updated_at_ms = ? WHERE technology_id = ?",
            (target.value, owner_decision_ref, now, now, technology_id),
        )
        return await self.get(technology_id)  # type: ignore[return-value]

    async def get(self, technology_id: str) -> TechnologyCapabilityRecord | None:
        row = await self.store.fetchone(
            "SELECT * FROM technology_capabilities WHERE technology_id = ?", (technology_id,)
        )
        if row is None:
            return None
        return TechnologyCapabilityRecord(
            technology_id=str(row["technology_id"]), name=str(row["name"]),
            category=str(row["category"]), version=row["version"], source=row["source"],
            licence=row["licence"], security_profile=row["security_profile"],
            strengths=json.loads(str(row["strengths_json"])),
            weaknesses=json.loads(str(row["weaknesses_json"])),
            integration_cost=row["integration_cost"], migration_risk=row["migration_risk"],
            owner_value=row["owner_value"],
            pipeline_state=PipelineState(str(row["pipeline_state"])),
            benchmark_digest=row["benchmark_digest"],
            owner_decision_ref=row["owner_decision_ref"],
            last_evaluated_at_ms=row["last_evaluated_at_ms"],
        )

    async def radar(self) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT technology_id, name, category, pipeline_state, version, "
            "last_evaluated_at_ms FROM technology_capabilities ORDER BY category, name"
        )
        return [dict(r) for r in rows]

    async def deprecations(self) -> list[dict[str, Any]]:
        """§84 — what VAN depends on that is going away."""
        rows = await self.store.fetchall(
            "SELECT * FROM technology_capabilities WHERE pipeline_state = 'DEPRECATED'"
        )
        return [dict(r) for r in rows]


# ------------------------------------------------------- §83 benchmark harness


class BenchmarkHarness:
    """§24 — VAN-specific suites. Provider branding never overrides evidence."""

    SUITES = (
        "project_architecture", "coding", "repository_reconciliation", "research",
        "browser_interaction", "factual_analysis", "critical_review", "planning",
        "memory_retrieval", "voice_command_understanding", "long_horizon_recovery",
        "tool_reliability", "cost", "latency",
    )

    def __init__(self, store: Store) -> None:
        self.store = store

    async def record_run(
        self,
        *,
        suite: str,
        results: list[dict[str, Any]],
        technology_id: str | None = None,
        median_latency_ms: int | None = None,
        total_cost_micros: int | None = None,
        now_ms: int | None = None,
    ) -> str:
        if suite not in self.SUITES:
            raise RadarError("BENCHMARK_SUITE_UNKNOWN", suite)
        now = int(time.time() * 1000) if now_ms is None else now_ms
        passed = sum(1 for r in results if r.get("passed"))
        run_id = f"bench_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO benchmark_runs(
              run_id, suite, technology_id, task_count, passed, failed, median_latency_ms,
              total_cost_micros, results_json, harness_version, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, suite, technology_id, len(results), passed, len(results) - passed,
                median_latency_ms, total_cost_micros, Store.dumps(results),
                HARNESS_VERSION, now,
            ),
        )
        return run_id

    async def latest(self, suite: str, technology_id: str | None = None) -> dict[str, Any] | None:
        if technology_id is None:
            row = await self.store.fetchone(
                "SELECT * FROM benchmark_runs WHERE suite = ? "
                "ORDER BY created_at_ms DESC LIMIT 1",
                (suite,),
            )
        else:
            row = await self.store.fetchone(
                "SELECT * FROM benchmark_runs WHERE suite = ? AND technology_id = ? "
                "ORDER BY created_at_ms DESC LIMIT 1",
                (suite, technology_id),
            )
        return None if row is None else dict(row)

    async def regressed(self, suite: str, technology_id: str) -> bool:
        """§84 — measured drift, which is what demotes a model.

        Two runs are the minimum: a single result is a measurement, not a trend,
        and demoting on one bad run would make VAN thrash on noise.
        """
        rows = await self.store.fetchall(
            "SELECT passed, task_count FROM benchmark_runs WHERE suite = ? "
            "AND technology_id = ? ORDER BY created_at_ms DESC LIMIT 2",
            (suite, technology_id),
        )
        if len(rows) < 2:
            return False
        newest, previous = rows[0], rows[1]
        if not newest["task_count"] or not previous["task_count"]:
            return False
        return (newest["passed"] / newest["task_count"]) < (
            previous["passed"] / previous["task_count"]
        )


# -------------------------------------------------------- §25 strategy learning


class PromotionState(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    SHADOW = "SHADOW"
    ADMITTED = "ADMITTED"
    PREFERRED = "PREFERRED"
    DEMOTED = "DEMOTED"
    FORBIDDEN = "FORBIDDEN"


class StrategyLearning:
    """§25 — which capability sequences work, promoted only on eval evidence.

    §27's boundaries apply: no uncontrolled self-modifying code and no automatic
    security-policy changes. This learns *ordering preferences among already
    declared capabilities* — it cannot invent a capability, widen one, or change
    what any of them is permitted to do.
    """

    #: DECISION (recorded): PREFERRED needs 10 runs at >=90% success. Chosen so a
    #: strategy cannot become the default off a lucky streak; §41 asks for
    #: "measurable strategy improvement in >=3 production mission classes", which
    #: needs a sample size that means something.
    PREFERRED_MIN_RUNS = 10
    PREFERRED_MIN_RATE = 0.9

    def __init__(self, store: Store) -> None:
        self.store = store

    async def register(
        self,
        *,
        mission_class: str,
        capability_sequence: list[str],
        conditions: dict[str, Any] | None = None,
        max_action_class: ActionClass = ActionClass.A1,
        now_ms: int | None = None,
    ) -> str:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        strategy_id = f"strat_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO execution_strategies(
              strategy_id, mission_class, capability_sequence_json, conditions_json,
              success_count, failure_count, median_latency_ms, median_cost_micros,
              verification_quality, promotion_state, eval_run_id, last_evaluated_at_ms,
              created_at_ms, updated_at_ms, max_action_class
            ) VALUES (?, ?, ?, ?, 0, 0, NULL, NULL, 0.0, 'EXPERIMENTAL', NULL, NULL, ?, ?, ?)
            """,
            (
                strategy_id, mission_class, Store.dumps(capability_sequence),
                Store.dumps(conditions or {}), now, now, max_action_class.value,
            ),
        )
        return strategy_id

    async def find_or_register(
        self,
        *,
        mission_class: str,
        capability_sequence: list[str],
        max_action_class: ActionClass = ActionClass.A1,
        now_ms: int | None = None,
    ) -> str:
        """The strategy for this exact sequence in this class, creating it if new.

        P1-LEARN-003 — a strategy is a thing VAN *did*, so it comes into existence by
        having been done. `capability_sequence_json` is written through `Store.dumps`,
        which is deterministic, so the same sequence matches itself exactly rather than
        through a fuzzy comparison that would merge two different plans.
        """
        encoded = Store.dumps(capability_sequence)
        row = await self.store.fetchone(
            "SELECT strategy_id, max_action_class FROM execution_strategies "
            "WHERE mission_class = ? AND capability_sequence_json = ?",
            (mission_class, encoded),
        )
        if row is None:
            return await self.register(
                mission_class=mission_class, capability_sequence=capability_sequence,
                max_action_class=max_action_class, now_ms=now_ms,
            )
        strategy_id = str(row["strategy_id"])
        # The ceiling records what this sequence has actually been run under, so it rises
        # to meet a real run and never beyond one. It is not a grant: `permitted_for`
        # compares it with the asking mission's envelope and refuses the wider strategy.
        if CLASS_RANK[ActionClass(str(row["max_action_class"]))] < CLASS_RANK[max_action_class]:
            await self.store.execute(
                "UPDATE execution_strategies SET max_action_class = ? WHERE strategy_id = ?",
                (max_action_class.value, strategy_id),
            )
        return strategy_id

    async def record_outcome(
        self, strategy_id: str, *, verified_success: bool, now_ms: int | None = None
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        column = "success_count" if verified_success else "failure_count"
        await self.store.execute(
            f"UPDATE execution_strategies SET {column} = {column} + 1, updated_at_ms = ? "
            "WHERE strategy_id = ?",
            (now, strategy_id),
        )

    async def promote(
        self,
        strategy_id: str,
        *,
        target: PromotionState,
        eval_run_id: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """§25 — promotion requires eval evidence, so it is refused without it."""
        row = await self.store.fetchone(
            "SELECT * FROM execution_strategies WHERE strategy_id = ?", (strategy_id,)
        )
        if row is None:
            raise RadarError("STRATEGY_UNKNOWN", strategy_id)
        if target in (PromotionState.ADMITTED, PromotionState.PREFERRED) and not eval_run_id:
            raise RadarError("STRATEGY_PROMOTION_REQUIRES_EVAL", strategy_id)
        if target is PromotionState.PREFERRED:
            runs = int(row["success_count"]) + int(row["failure_count"])
            rate = int(row["success_count"]) / runs if runs else 0.0
            if runs < self.PREFERRED_MIN_RUNS or rate < self.PREFERRED_MIN_RATE:
                raise RadarError(
                    "STRATEGY_INSUFFICIENT_EVIDENCE",
                    f"{runs} runs at {rate:.0%}; need >= {self.PREFERRED_MIN_RUNS} "
                    f"at {self.PREFERRED_MIN_RATE:.0%}",
                )
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE execution_strategies SET promotion_state = ?, eval_run_id = ?, "
            "last_evaluated_at_ms = ?, updated_at_ms = ? WHERE strategy_id = ?",
            (target.value, eval_run_id, now, now, strategy_id),
        )
        return dict(
            await self.store.fetchone(
                "SELECT * FROM execution_strategies WHERE strategy_id = ?", (strategy_id,)
            )
        )

    async def auto_demote(self, *, now_ms: int | None = None) -> list[str]:
        """§41 — regression auto-demotion exists.

        Demotion is automatic where promotion is not, and deliberately so:
        removing trust from something that stopped working needs no ceremony,
        while granting it does.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        rows = await self.store.fetchall(
            "SELECT strategy_id, success_count, failure_count FROM execution_strategies "
            "WHERE promotion_state IN ('ADMITTED','PREFERRED')"
        )
        demoted = []
        for row in rows:
            runs = int(row["success_count"]) + int(row["failure_count"])
            if runs < 3:
                continue
            if int(row["success_count"]) / runs < 0.6:
                await self.store.execute(
                    "UPDATE execution_strategies SET promotion_state = 'DEMOTED', "
                    "updated_at_ms = ? WHERE strategy_id = ?",
                    (now, row["strategy_id"]),
                )
                demoted.append(str(row["strategy_id"]))
        return demoted

    async def preferred_for(self, mission_class: str) -> list[dict[str, Any]]:
        """Every PREFERRED strategy for this class, regardless of what it needs.

        This is the *reporting* view — what VAN has learned — and it is deliberately not
        the one anything acts on. `permitted_for` is that one.
        """
        rows = await self.store.fetchall(
            "SELECT * FROM execution_strategies WHERE mission_class = ? "
            "AND promotion_state = 'PREFERRED' ORDER BY updated_at_ms DESC",
            (mission_class,),
        )
        return [dict(r) for r in rows]

    async def permitted_for(
        self, mission_class: str, *, envelope_max_action_class: ActionClass
    ) -> list[dict[str, Any]]:
        """P1-LEARN-002 — what a mission with *this* envelope may be offered.

        §27 forbids uncontrolled self-modification, and the quiet way to breach it is not
        to write new code: it is for a sequence proven under an A4 mission to be offered
        back as the preferred approach to a mission the owner capped at A2. Nobody widened
        anything; authority would simply have been acquired by accumulation.

        So the ceiling a strategy was exercised under is compared with the envelope of the
        mission asking, and a strategy that needs more is not offered. It is not demoted
        or hidden — it is still PREFERRED and still visible in `preferred_for` — it is just
        not an answer to this question.
        """
        ceiling = CLASS_RANK[envelope_max_action_class]
        return [
            row for row in await self.preferred_for(mission_class)
            if CLASS_RANK[ActionClass(str(row["max_action_class"]))] <= ceiling
        ]


__all__ = [
    "HARNESS_VERSION",
    "AIEvolutionRadar",
    "BenchmarkHarness",
    "ExternalRealityModel",
    "PipelineState",
    "PromotionState",
    "RadarError",
    "StrategyLearning",
    "TechnologyCapabilityRecord",
]
