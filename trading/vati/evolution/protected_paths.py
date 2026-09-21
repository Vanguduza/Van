"""Protected-path enforcement for model-authored evolution (TRD-REV51-126)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PROTECTED_PATH_PREFIXES = (
    "trading/vati/risk/authority.py",
    "trading/vati/execution/router.py",
    "trading/vati/risk/mandate.py",
    "trading/vati/risk/governor.py",
    "trading/vati/execution/protection.py",
    "backend/van_gateway/authority/",
    "backend/van_gateway/trading/",
    "registries/owner_authority",
    "trading/vati/evolution/admission.py",
)
PROTECTED_TEXT_MARKERS = (
    "class RiskAuthority",
    "class ExecutionRouter",
    "OrderCommand(",
    "max_risk_per_trade",
    "max_open_stop_risk",
    "kill_switch",
    "LIVE_ADVISORY",
    "EXPANSION_MODE = Mode.LIVE",
    "control_profile",
    "ProposalAdmission",
)


@dataclass(frozen=True)
class ProtectedPathScan:
    touched_paths: tuple[str, ...]
    marker_hits: tuple[str, ...]
    requires_authorised_review: bool

    @property
    def clean(self) -> bool:
        return not self.requires_authorised_review


class ProtectedPathPolicy:
    def scan(self, paths: Iterable[str], *, diff_text: str = "") -> ProtectedPathScan:
        path_hits = tuple(sorted({
            str(path) for path in paths
            if any(str(path).startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES)
        }))
        marker_hits = tuple(sorted({
            marker for marker in PROTECTED_TEXT_MARKERS if marker in diff_text
        }))
        return ProtectedPathScan(
            touched_paths=path_hits,
            marker_hits=marker_hits,
            requires_authorised_review=bool(path_hits or marker_hits),
        )

    def enforce(self, scan: ProtectedPathScan, *, authorised_review: bool) -> None:
        if scan.requires_authorised_review and not authorised_review:
            raise PermissionError(
                "model-authored change touches a protected path and has no authorised review")
