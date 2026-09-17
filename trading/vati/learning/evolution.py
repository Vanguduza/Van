"""Strategy evolution (integration doc §21): cluster failures by context,
propose a versioned candidate in RESEARCH. The old version is preserved; the
new one takes the normal owner-signed promotion path."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from vati.learning.episodes import ExperienceEpisode
from vati.strategies.capsule import Capsule, CapsuleRegistry

ZERO = Decimal("0")


@dataclass(frozen=True)
class FailureCluster:
    strategy_id: str
    context_key: str          # e.g. "vol=HIGH|session=ASIA|event=QUIET"
    episodes: int
    weighted_episodes: Decimal
    mean_r: Decimal
    share_of_losses: Decimal


@dataclass(frozen=True)
class StrategyCandidate:
    parent_strategy_id: str
    parent_version: str
    candidate_strategy_id: str
    candidate_version: str
    hypothesis: str
    added_constraints: tuple[str, ...]
    supporting_clusters: tuple[FailureCluster, ...]
    state: str = "RESEARCH"


def cluster_failures(episodes: Iterable[ExperienceEpisode], *, context_fn) -> list[FailureCluster]:
    """context_fn(episode) → context string. Clusters losing episodes by context."""
    by_strat: dict[str, list[ExperienceEpisode]] = defaultdict(list)
    for e in episodes:
        by_strat[e.strategy_id].append(e)
    out: list[FailureCluster] = []
    for sid, eps in by_strat.items():
        losses = [e for e in eps if e.outcome.get("r_multiple") is not None and Decimal(str(e.outcome["r_multiple"])) < ZERO]
        if not losses:
            continue
        groups: dict[str, list[ExperienceEpisode]] = defaultdict(list)
        for e in losses:
            groups[context_fn(e)].append(e)
        total_w = sum((e.weight() for e in losses), ZERO)
        for key, g in groups.items():
            w = sum((e.weight() for e in g), ZERO)
            mean_r = sum((Decimal(str(e.outcome["r_multiple"])) * e.weight() for e in g), ZERO) / w
            out.append(FailureCluster(sid, key, len(g), w, mean_r.quantize(Decimal("0.01")), (w / total_w).quantize(Decimal("0.01")) if total_w else ZERO))
    return sorted(out, key=lambda c: (-c.share_of_losses, c.strategy_id, c.context_key))


def propose_candidate(registry: CapsuleRegistry, cluster: FailureCluster, *, constraint: str, hypothesis: str, min_weighted_episodes: Decimal = Decimal("10")) -> tuple[StrategyCandidate, Capsule]:
    if cluster.weighted_episodes < min_weighted_episodes:
        raise ValueError(f"cluster too small for a candidate: {cluster.weighted_episodes} < {min_weighted_episodes} weighted episodes")
    parent = registry.get(cluster.strategy_id)
    family, num = parent.strategy_id.rsplit("-", 1)
    new_id = f"{family}-{int(num) + 1:02d}"
    new_capsule = Capsule(CapsuleRegistry.seal({**parent.data, "strategy_id": new_id, "version": "1.0.0", "state": "RESEARCH", "supersedes": parent.capsule_hash,
                                                "evidence_refs": [], "approval_signature_ref": None, "approved_at_unix": None,
                                                "forbidden_regimes": sorted(set(parent.data["forbidden_regimes"]) | {constraint}),
                                                "invalidation_logic_ref": f"{parent.data['invalidation_logic_ref']}; candidate constraint: {constraint}"}))
    registry.add(new_capsule)
    cand = StrategyCandidate(parent.strategy_id, parent.version, new_id, "1.0.0", hypothesis, (constraint,), (cluster,))
    return cand, new_capsule
