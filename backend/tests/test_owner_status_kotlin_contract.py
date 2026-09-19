"""The gateway and the device must agree on what a status means to the owner.

P2-COH-001 and P0-EXEC-003 are the same defect on two sides of the wire: each surface
decided for itself what a status meant, and the decisions disagreed. Fixing both and
leaving them as two independent tables would only postpone the drift.

This test parses the Kotlin and compares it to the Python. It is the same technique the
repository already uses to keep the MCP registration in step with the shim, and it is the
reason the Kotlin tables are written one entry per line.

What it cannot do is prove the device *uses* the table — that is what the Kotlin tests in
android/verification assert, and they are executed, not merely written.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from van_gateway.coherence.owner_status import NEEDS_OWNER, FINISHED, SENTENCE, OwnerWorkStatus
from van_gateway.coherence.wire_status import COMMAND_RESULT, MISSION_STATE

ROOT = Path(__file__).resolve().parents[2]
KOTLIN = ROOT / "android/app/src/main/java/com/dial/van/status/OwnerWorkStatus.kt"
KOTLIN_STATUS = ROOT / "android/app/src/main/java/com/dial/van/status/VanCommandStatus.kt"


@pytest.fixture(scope="module")
def kotlin() -> str:
    assert KOTLIN.is_file(), f"{KOTLIN} is missing; the device has no projection"
    return KOTLIN.read_text(encoding="utf-8")


def _block(source: str, name: str) -> str:
    """The body of a `val <name>: ... = mapOf(...)` or `setOf(...)` declaration."""
    match = re.search(rf"val {re.escape(name)}\b[^=]*=\s*\w+\(", source)
    assert match, f"{name} not found in the Kotlin projection"
    start = match.end()
    depth = 1
    for i in range(start, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                return source[start:i]
    raise AssertionError(f"unbalanced parentheses reading {name}")


def _string_map(source: str, name: str) -> dict[str, str]:
    return {
        key: value
        for key, value in re.findall(
            r'"([^"]+)"\s+to\s+OwnerWorkStatus\.([A-Z_]+)', _block(source, name)
        )
    }


def _status_set(source: str, name: str) -> set[str]:
    return set(re.findall(r"OwnerWorkStatus\.([A-Z_]+)", _block(source, name)))


def test_the_owner_status_enums_are_identical(kotlin):
    body = re.search(r"enum class OwnerWorkStatus \{(.*?)\n\}", kotlin, re.S).group(1)
    kotlin_members = [m for m in re.findall(r"^\s{4}([A-Z_]+),", body, re.M)]
    assert kotlin_members == [s.value for s in OwnerWorkStatus]


def test_the_command_result_projections_agree(kotlin):
    assert _string_map(kotlin, "commandResult") == {
        wire: status.value for wire, status in COMMAND_RESULT.items()
    }


def test_the_mission_state_projections_agree(kotlin):
    assert _string_map(kotlin, "missionState") == {
        state: status.value for state, status in MISSION_STATE.items()
    }


def test_the_sentences_agree_word_for_word(kotlin):
    kotlin_sentences = dict(
        re.findall(r'OwnerWorkStatus\.([A-Z_]+)\s+to\s+"([^"]*)"', _block(kotlin, "sentence"))
    )
    assert kotlin_sentences == {status.value: text for status, text in SENTENCE.items()}


def test_the_attention_and_finished_sets_agree(kotlin):
    assert _status_set(kotlin, "needsOwner") == {s.value for s in NEEDS_OWNER}
    assert _status_set(kotlin, "finished") == {s.value for s in FINISHED}


def test_neither_side_keeps_a_benign_default(kotlin):
    """The defect, asserted as source text on the side that had it."""
    controller = (
        ROOT / "android/app/src/main/java/com/dial/van/control/VanCommandController.kt"
    ).read_text(encoding="utf-8")
    assert "else -> VanCommandStatus.ACCEPTED" not in controller, (
        "the status when-expression fell through to ACCEPTED again"
    )
    assert "OwnerWorkStatus.UNKNOWN" in kotlin
    assert "?: OwnerWorkStatus.UNKNOWN" in kotlin


def test_the_message_status_mapping_has_no_catch_all():
    """An `else` here would let a new owner status silently pick a neighbour's rendering."""
    source = KOTLIN_STATUS.read_text(encoding="utf-8")
    mapping = re.search(
        r"fun commandStatusFor\(owner: OwnerWorkStatus\): VanCommandStatus = when \(owner\) \{(.*?)\n\}",
        source,
        re.S,
    )
    assert mapping, "commandStatusFor is missing"
    assert "else ->" not in mapping.group(1)
    covered = set(re.findall(r"OwnerWorkStatus\.([A-Z_]+)\s*->", mapping.group(1)))
    assert covered == {s.value for s in OwnerWorkStatus}


def test_the_verification_harness_compiles_the_real_source_not_a_copy():
    """A harness pointed at a copy would prove nothing about what the app ships."""
    build = (ROOT / "android/verification/build.gradle.kts").read_text(encoding="utf-8")
    assert 'kotlin.srcDir("../app/src/main/java")' in build
