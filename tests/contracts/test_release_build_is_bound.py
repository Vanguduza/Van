"""Rev 1.5 §§0D.2, 0D.3 — what a release build must be before it is allowed to exist.

RB-111 and RB-121. Four things have to be true of a production APK, and none of them can
be discovered after the fact from the artefact:

* it is signed by a **stable** identity, not the per-machine Android debug key. §0D.3's
  binding is "this package + this app signing identity + this hardware Keystore key + this
  Gateway owner-device slot", and a debug key is whichever machine ran the build. The
  owner's first sideload failed with the dialog for exactly that (P2-AND-016);
* it points at an HTTPS Gateway;
* it carries a **connectivity trust anchor**. §0D.2 removed every field the owner could
  type an endpoint into, so a build with no anchor can never accept a manifest and can
  never be provisioned. It installs, opens, and sits on "waiting for the installer"
  forever with nothing saying why;
* it has a keystore at all.

**What this file verifies and what it does not.** The Android Gradle Plugin is unreachable
in the audit container, so no test here runs `assembleRelease`. What is checked is that the
gate exists in the build script, that it fires on the release task graph rather than on
every build, and that the predicate it uses actually rejects the inputs it is supposed to —
the last by re-implementing that one predicate here and running it against a table. A gate
present but wrong is the failure this last part exists to catch; a gate correct but never
executed is CI's to prove, and it is the reason `assembleRelease` runs there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "android/app/build.gradle.kts"


def _gate() -> str:
    """The release-only block. Everything asserted below has to be inside it."""
    text = BUILD.read_text(encoding="utf-8")
    start = text.index("gradle.taskGraph.whenReady")
    return text[start: text.index("compileOptions {", start)]


def test_the_gate_fires_only_on_a_release_task_graph():
    """A gate that fired on every build would make a debug build impossible.

    Which sounds harmless and is not: a contributor whose debug build refuses to compile
    removes the check, and it is gone for the release too.
    """
    gate = _gate()
    assert 'n == "assembleRelease" || n == "bundleRelease"' in gate
    assert "if (releaseRequested) {" in gate


def test_a_release_may_not_be_signed_by_the_android_debug_key():
    """RB-111 — by name, because the fingerprint is not knowable at configuration time.

    What is knowable is that `androiddebugkey` and `debug.keystore` are never a production
    identity, and those are the two spellings a machine-generated key actually has.
    """
    gate = _gate()
    assert 'alias == "androiddebugkey"' in gate
    assert 'storePath.trim().endsWith("debug.keystore")' in gate
    assert "Rev 1.5 §0D.3" in gate


def test_a_release_may_not_ship_without_a_connectivity_trust_anchor():
    """RB-121 — the one that turns a shipped APK into a brick nobody can diagnose."""
    gate = _gate()
    assert "VAN_CONNECTIVITY_TRUSTED_KEYS" in gate
    assert "vanConnectivityTrustedKeys.split" in gate
    assert "BEGIN PUBLIC KEY" in gate, (
        "presence is not enough: a truncated argument parses to no keys and looks configured"
    )


def test_a_release_may_not_point_at_a_plain_http_gateway():
    assert 'vanGatewayBaseUrl.startsWith("https://")' in _gate()


def test_a_release_may_not_ship_unsigned():
    gate = _gate()
    assert "keystorePropertiesFile.exists()" in gate
    assert "storeFile missing or not found" in gate


# --------------------------------------------------------------------------- the predicate


def _anchors(raw: str) -> list[str]:
    """The Gradle gate's anchor filter, re-implemented line for line.

    A transcription, deliberately: it is here to be compared against the Kotlin above by
    eye and to be run against inputs that Gradle cannot be asked about in this container.
    If the two drift, `test_the_transcription_matches_the_gradle_source` fails.
    """
    return [
        line.strip() for line in raw.split("\n")
        if "=" in line.strip() and "BEGIN PUBLIC KEY" in line.strip().split("=", 1)[1]
    ]


PEM = "-----BEGIN PUBLIC KEY-----\\nAAAA\\n-----END PUBLIC KEY-----"


@pytest.mark.parametrize(
    "raw, accepted",
    [
        (f"prov-1={PEM}", True),
        (f"prov-1={PEM}\nprov-2={PEM}", True),
        ("", False),
        ("   ", False),
        # The failure the presence check alone would miss: a value that looks configured.
        ("prov-1=", False),
        ("prov-1=hunter2", False),
        ("nonsense", False),
        # One good line among rubbish is still an anchor; a build with a usable key is not
        # refused because something else in the argument was malformed.
        (f"nonsense\nprov-1={PEM}", True),
    ],
)
def test_the_anchor_predicate_rejects_what_it_should(raw, accepted):
    assert bool(_anchors(raw)) is accepted, raw


def test_the_transcription_matches_the_gradle_source():
    """The predicate above is a copy, so this is what stops it becoming a stale one.

    Compared as the three conditions it is made of rather than as a string, because the
    Kotlin and the Python cannot be spelled the same and a whitespace diff would make this
    test fail for no reason anyone could act on.
    """
    gate = _gate()
    filter_block = gate[gate.index("val anchors ="): gate.index("if (anchors.isEmpty())")]
    assert ".split(" in filter_block
    assert "trim()" in filter_block
    assert "contains('=')" in filter_block
    assert 'substringAfter(\'=\').contains("BEGIN PUBLIC KEY")' in filter_block


def test_the_gate_names_the_sections_it_enforces():
    """So the next person to hit it can find out why rather than deleting it."""
    gate = _gate()
    for citation in ("§0D.3", "§0D.2", "ADR-RB-026"):
        assert citation in gate, citation
