"""Rev 1.5 §32 — the build may only use dependencies that were actually measured.

`registries/remote_browser_dependencies.json` records a digest computed by downloading each
artefact. That record is worth something only while the build is using the same version: a
bump in `app/build.gradle.kts` leaves the registry describing an artefact nobody is
shipping, and the digest then certifies a file that is not in the APK.

So this reads both and compares. It does not re-download anything — that happens when a
dependency is admitted, and pretending a test run is a supply-chain check would be the
§42.5 failure ("integrated because a dependency exists") one layer down.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries" / "remote_browser_dependencies.json"
GRADLE = ROOT / "android" / "app" / "build.gradle.kts"


def _registry() -> dict:
    return json.loads(REGISTRY.read_text())


def _declared() -> set[str]:
    """Every `group:artifact:version` the app module declares."""
    return set(
        re.findall(
            r'(?:implementation|api|compileOnly|runtimeOnly)\("([^"]+:[^"]+:[^"]+)"\)',
            GRADLE.read_text(),
        )
    )


def test_every_measured_android_dependency_is_the_one_the_build_uses():
    declared = _declared()
    for name, entry in _registry()["android"].items():
        assert entry["coordinate"] in declared, (
            f"{name} is pinned in the registry as {entry['coordinate']} but the build "
            f"declares something else; the recorded digest describes an artefact that is "
            f"not in the APK"
        )


def test_nothing_is_admitted_without_a_verified_digest():
    for name, entry in _registry()["android"].items():
        assert entry["pin_status"] == "PINNED_DIGEST_VERIFIED", name
        assert re.fullmatch(r"[0-9a-f]{64}", entry["artifact_sha256"]), name
        assert entry["artifact_bytes"] > 0, name


def test_every_admitted_dependency_names_its_adoption_decision():
    """§32 — a dependency without a decision is one nobody chose."""
    for name, entry in _registry()["android"].items():
        decision = ROOT / entry["adoption_decision_ref"]
        assert decision.exists(), f"{name} cites a decision that does not exist: {decision}"


def test_the_rejected_candidate_is_not_quietly_back_in_the_build():
    """okhttp 5.x was rejected on a measured incompatibility, not a preference.

    The failure this prevents is the ordinary one: someone upgrades, the Kotlin metadata
    version fails at compile time, and the registry still explains why it was rejected
    while the build does the opposite.
    """
    declared = _declared()
    for entry in _registry()["android"].values():
        deviation = entry.get("deviation_from_blueprint")
        if deviation:
            assert deviation["blueprint_candidate"] not in declared, (
                f"{deviation['blueprint_candidate']} is declared but the registry records "
                f"it as rejected: {deviation['rejected_because']}"
            )


def test_the_abi_filter_matches_the_one_the_registry_justifies():
    """Shipping an ABI the decision does not cover is 35 MB nobody argued for."""
    gradle = GRADLE.read_text()
    filters = set(re.findall(r'abiFilters \+= "([^"]+)"', gradle))
    expected = set(_registry()["android"]["webrtc"]["production_abi_filter"])
    assert filters == expected, (
        f"the build filters to {sorted(filters)} and the registry justifies "
        f"{sorted(expected)}"
    )


def test_no_remote_browser_dependency_floats():
    """§32 forbids a floating version. A `+` is a different artefact every build."""
    for coordinate in _declared():
        assert "+" not in coordinate, coordinate
        assert not coordinate.endswith("-SNAPSHOT"), coordinate


def test_what_is_not_installed_says_so():
    """The stream host's runtimes are not in this repository and must not read as pinned."""
    for name, entry in _registry()["stream_host"].items():
        if name.startswith("$"):
            continue
        assert entry["pin_status"] == "EXTERNAL_UNPROVISIONED", (
            f"{name} claims a pin status this repository cannot support: nothing here "
            f"installs it"
        )
