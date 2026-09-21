"""Rev 1.5 §§26, 27 — quality adaptation, and the two SLO profiles it is judged against.

§26.2 is the part that matters most and is easiest to get wrong: **a metered session is not
failed merely because it does not reach the unmetered target.** It fails if it misses the
metered profile, or if the UI reports high-quality certification it did not earn. So the
profiles are separate objects with separate thresholds, and the verdict always names which
one it was measured against.

§27.2's rule is stated in the negative and is the reason metered is the default: the app
must not silently consume 4–12 Mbps for hours of someone's mobile data. An owner who wants
that can have it, per session, by asking.

Hysteresis (§27.4) is not decoration. Without it a connection sitting on a threshold
oscillates, and the owner sees a quality badge flickering rather than a stable picture —
which reads as instability even when the stream is fine.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class QualityMode(str, Enum):
    """§27.1 — the ladder, worst to best. Ordered so comparisons mean what they read."""

    SURVIVAL = "SURVIVAL"
    CONSTRAINED = "CONSTRAINED"
    NORMAL = "NORMAL"
    ULTRA = "ULTRA"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {
    QualityMode.SURVIVAL: 0,
    QualityMode.CONSTRAINED: 1,
    QualityMode.NORMAL: 2,
    QualityMode.ULTRA: 3,
}


@dataclass(frozen=True)
class QualityTarget:
    """What a mode asks the encoder for."""

    mode: QualityMode
    max_height: int
    fps: int
    bitrate_kbps: int


#: §27.1 — the unmetered ladder.
UNMETERED_LADDER: dict[QualityMode, QualityTarget] = {
    QualityMode.ULTRA: QualityTarget(QualityMode.ULTRA, 1080, 60, 8_000),
    QualityMode.NORMAL: QualityTarget(QualityMode.NORMAL, 1080, 60, 5_000),
    QualityMode.CONSTRAINED: QualityTarget(QualityMode.CONSTRAINED, 900, 45, 3_000),
    QualityMode.SURVIVAL: QualityTarget(QualityMode.SURVIVAL, 720, 30, 1_500),
}

#: §27.2 — the metered ceiling. Note that ULTRA is absent rather than capped: on metered
#: data the highest mode VAN offers *is* NORMAL-at-720p, and pretending otherwise would put
#: a quality badge on the screen that the bitrate does not support.
METERED_LADDER: dict[QualityMode, QualityTarget] = {
    QualityMode.NORMAL: QualityTarget(QualityMode.NORMAL, 720, 45, 3_000),
    QualityMode.CONSTRAINED: QualityTarget(QualityMode.CONSTRAINED, 720, 30, 2_000),
    QualityMode.SURVIVAL: QualityTarget(QualityMode.SURVIVAL, 540, 30, 1_000),
}


@dataclass(frozen=True)
class SloProfile:
    """§26.1 / §26.2 — what "good" means, and which regime it was measured in."""

    name: str
    max_rtt_ms: int
    touch_to_visible_p95_ms: int
    min_rendered_fps_p95: int
    max_packet_loss: float
    takeover_ack_ms: int


UNMETERED_SLO = SloProfile(
    name="unmetered",
    max_rtt_ms=80,
    touch_to_visible_p95_ms=130,
    min_rendered_fps_p95=55,
    max_packet_loss=0.02,
    takeover_ack_ms=100,
)

METERED_SLO = SloProfile(
    name="metered",
    # §26.3 — mobile RTT is the one budget the phone cannot spend its way out of.
    max_rtt_ms=150,
    touch_to_visible_p95_ms=150,
    min_rendered_fps_p95=30,
    max_packet_loss=0.05,
    takeover_ack_ms=150,
)


@dataclass(frozen=True)
class LinkSample:
    """§27 — one observation of the link and the machines at each end."""

    rtt_ms: float
    jitter_ms: float
    packet_loss: float
    available_bitrate_kbps: float
    encode_ms: float
    capture_ms: float
    rendered_fps: float
    metered: bool
    #: §27.2 — a per-session owner override, not a stored preference.
    owner_allows_high_quality_on_metered: bool = False


class SessionQualityStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    #: §26.3 — the link itself cannot meet the interaction budget. Not VAN's failure, and
    #: reporting it as one would send the owner looking in the wrong place.
    NETWORK_LIMITED = "NETWORK_LIMITED"


@dataclass(frozen=True)
class QualityVerdict:
    mode: QualityMode
    target: QualityTarget
    status: SessionQualityStatus
    profile: SloProfile
    reason: str

    @property
    def certified_high_quality(self) -> bool:
        """§26.2 — only ever true under the unmetered profile.

        This exists as a property rather than a flag a caller can set, because the failure
        §26.2 names is the telemetry *claiming* high-quality certification it did not earn.
        """
        return self.profile is UNMETERED_SLO and self.status is SessionQualityStatus.OK


#: §27.4 — how much better than the next rung a link must be before moving up.
#:
#: Asymmetric on purpose: dropping quality is cheap and immediate, raising it is what
#: oscillates. A link must beat the higher rung's requirement by this margin, and hold it.
UPGRADE_MARGIN = 1.25
#: Consecutive samples that must agree before an upgrade is applied.
UPGRADE_STREAK = 3


@dataclass
class BrowserQualityController:
    """§27 — one per session. Feed it samples, read a mode.

    Downgrades apply immediately; upgrades need a streak. A controller that upgraded as
    eagerly as it downgrades would chase every transient improvement, and the owner would
    see the badge change more often than the page.
    """

    mode: QualityMode = QualityMode.NORMAL
    _streak: int = 0
    #: §27.3 — per-session accounting, for telemetry rather than billing.
    media_bytes_received: int = 0
    media_bytes_sent: int = 0
    control_bytes: int = 0
    samples: int = 0

    def ladder(self, sample: LinkSample) -> dict[QualityMode, QualityTarget]:
        if sample.metered and not sample.owner_allows_high_quality_on_metered:
            return METERED_LADDER
        return UNMETERED_LADDER

    def profile(self, sample: LinkSample) -> SloProfile:
        if sample.metered and not sample.owner_allows_high_quality_on_metered:
            return METERED_SLO
        return UNMETERED_SLO

    def observe(self, sample: LinkSample) -> QualityVerdict:
        self.samples += 1
        ladder = self.ladder(sample)
        profile = self.profile(sample)
        ceiling = max(ladder, key=lambda m: m.rank)

        wanted = self._mode_for(sample, ladder)
        if wanted.rank < self.mode.rank:
            # Down immediately: the link has already failed to carry what we are sending.
            self.mode = wanted
            self._streak = 0
        elif wanted.rank > self.mode.rank:
            self._streak += 1
            if self._streak >= UPGRADE_STREAK:
                # One rung at a time, even if the link looks capable of two. Jumping the
                # ladder is how an upgrade turns straight back into a downgrade.
                self.mode = _next_up(self.mode, ladder)
                self._streak = 0
        else:
            self._streak = 0

        if self.mode.rank > ceiling.rank or self.mode not in ladder:
            # Switching to a metered network mid-session lowers the ceiling under us.
            self.mode = ceiling

        status, reason = self._status(sample, profile)
        return QualityVerdict(
            mode=self.mode, target=ladder[self.mode], status=status,
            profile=profile, reason=reason,
        )

    def _mode_for(
        self, sample: LinkSample, ladder: dict[QualityMode, QualityTarget]
    ) -> QualityMode:
        """Which rung this sample can actually sustain."""
        best = min(ladder, key=lambda m: m.rank)
        for mode in sorted(ladder, key=lambda m: m.rank):
            target = ladder[mode]
            needed = target.bitrate_kbps
            if mode.rank > self.mode.rank:
                needed *= UPGRADE_MARGIN
            if sample.available_bitrate_kbps >= needed and sample.packet_loss <= 0.1:
                best = mode
        return best

    def _status(
        self, sample: LinkSample, profile: SloProfile
    ) -> tuple[SessionQualityStatus, str]:
        if sample.rtt_ms > profile.max_rtt_ms * 2:
            # §26.3 — no encoder setting fixes a round trip. Say so rather than degrading
            # the picture and leaving the owner wondering why it did not help.
            return (
                SessionQualityStatus.NETWORK_LIMITED,
                f"round trip {sample.rtt_ms:.0f}ms against a {profile.max_rtt_ms}ms budget",
            )
        if sample.rendered_fps < profile.min_rendered_fps_p95:
            return (
                SessionQualityStatus.DEGRADED,
                f"{sample.rendered_fps:.0f} fps against the {profile.name} floor of "
                f"{profile.min_rendered_fps_p95}",
            )
        if sample.packet_loss > profile.max_packet_loss:
            return (
                SessionQualityStatus.DEGRADED,
                f"{sample.packet_loss:.1%} packet loss against the {profile.name} ceiling of "
                f"{profile.max_packet_loss:.0%}",
            )
        return SessionQualityStatus.OK, f"within the {profile.name} profile"

    def account(
        self, *, media_received: int = 0, media_sent: int = 0, control: int = 0
    ) -> None:
        """§27.3 — per-session data, so the owner can see what a session cost them."""
        self.media_bytes_received += media_received
        self.media_bytes_sent += media_sent
        self.control_bytes += control

    def owner_summary(self, sample: LinkSample) -> dict[str, object]:
        """§27.2 — what the app shows. Plain words, and the honest name for the regime."""
        verdict = self.observe(replace(sample))
        megabytes = (self.media_bytes_received + self.media_bytes_sent) / 1_000_000
        return {
            "quality_mode": verdict.mode.value,
            "network": "mobile data" if sample.metered else "wi-fi",
            "metered": sample.metered,
            "profile": verdict.profile.name,
            "status": verdict.status.value,
            "reason": verdict.reason,
            "data_used_mb": round(megabytes, 2),
            "estimated_mbps": round(verdict.target.bitrate_kbps / 1000, 1),
            "high_quality_certified": verdict.certified_high_quality,
        }


def _next_up(
    mode: QualityMode, ladder: dict[QualityMode, QualityTarget]
) -> QualityMode:
    higher = [m for m in ladder if m.rank > mode.rank]
    return min(higher, key=lambda m: m.rank) if higher else mode
