"""The Android side of protocol rule 31, enforced rather than swept by hand.

`tools/audit/reachability.py` has answered "what does nothing reach?" for the gateway since
Gate 0. The Android module had no equivalent, and that is where this programme's most
expensive defect lived: `P0-AND-012` was four Kotlin compile errors on a branch nobody could
build, invisible because the Android Gradle Plugin cannot be fetched here and CI was not
running on the branch.

A compiler finds those. It does not find a screen nobody navigates to or a data layer nobody
constructs, which is the class this guards. `tools/audit/kotlin_reachability.py` found one on
its first run: `MissionRepository`, 371 lines whose own docstring says it is "the only place
the surfaces get data", referenced by no production file. The component ledger already
recorded that honestly as NEVER_CONSTRUCTED / WIRE, which is the reassuring half — the
scanner agreed with the ledger rather than contradicting it. The point of this test is that
the *next* one is caught the day it appears rather than on the day someone sweeps again.

Both lists below carry a reason per entry. An allowlist without reasons decays into a list
of things somebody once decided not to look at.
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "tools" / "audit" / "kotlin_reachability.py"

#: Files that nothing references and that is correct, with why. Adding an entry here is a
#: decision to be defended in review, not a way to silence the scanner.
EXPLAINED_UNREFERENCED: dict[str, str] = {
    "android/app/src/main/java/com/dial/van/visual/VanLivingFieldPreviews.kt": (
        "@Preview composables. Android Studio renders them; nothing calls them, by design. "
        "They are a development surface, not a shipping one."
    ),
    # docs/design/COMPONENT_CATALOGUE.md's own catalogue, built ahead of the surfaces that
    # adopt each one — `com.dial.van.design` builds the full component set once rather than
    # growing it screen-by-screen, and `tools/audit/android_design_lint.py`'s baseline
    # already tracks every screen package that has not migrated onto it yet. This worker
    # adopted VanScreen/VanPanel/StatusChip/MetricTile/LiveBadge/SectionHeader/AttentionItem/
    # TimelineRail/EmptyState/VanPressable across Home/Attention/Work/Connected/Settings.
    #
    # PositionCard, ThesisCard, EvidenceRow, FindingCard, HeatBar and ApprovalSheet were
    # reserved here for the trading worker, who has since rebuilt `trading/ui/**` onto the
    # design system (OverviewScreen/PositionsScreen/PositionDetailScreen/PotentialScreen/
    # HistoryScreen adopt all six) — none of them are unreferenced any more, so their
    # entries are removed rather than kept as stale excuses (see
    # `test_every_explained_entry_still_describes_something_real`).
}

#: Production symbols reached only from tests. Each is the TEST_ONLY maturity class and must
#: be tracked as a component with a disposition, not quietly tolerated here.
#:
#: Empty, and it has been non-empty. `MissionRepository` sat here with a paragraph saying
#: the six owner mission surfaces it was written for were rendered nowhere. P2-AND-015 built
#: one, and `test_every_explained_entry_still_describes_something_real` failed the moment it
#: did — which is the whole reason that test exists. An allowlist that outlives what it
#: excused is how one becomes a blanket.
EXPLAINED_TEST_ONLY: dict[str, str] = {}


@functools.lru_cache(maxsize=1)
def _scan() -> dict:
    """Cached: the sweep reads every Kotlin file in the module and six tests want it.

    Without this the suite pays ~3s per test for an answer that cannot change within a run.
    """
    result = subprocess.run(
        [sys.executable, str(SCANNER), "--json"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_scanner_runs_and_sees_the_module():
    report = _scan()
    assert report["files"] > 100, "the scanner found almost no Kotlin; its path is probably wrong"


def test_the_manifest_components_are_components_and_not_permissions():
    """The scanner's first version matched every `android:name` in the manifest.

    That put ACCESS_NETWORK_STATE, MAIN and LAUNCHER into the entry-point set. Harmless
    until a class shares a name with one of them and is silently treated as
    platform-instantiated — a scanner that hides exactly what it exists to find.
    """
    report = _scan()
    entry_points = set(report["entry_points"])
    assert entry_points, "no manifest components found; the manifest parse is broken"
    for not_a_class in ("ACCESS_NETWORK_STATE", "MAIN", "LAUNCHER", "INTERNET", "RECORD_AUDIO"):
        assert not_a_class not in entry_points

    # The components that must be there, named, so a manifest edit that drops one is a
    # failure rather than a smaller set the scanner reports as fine.
    for component in ("VanApplication", "CommandCentreActivity", "WakeListenerService"):
        assert component in entry_points


def test_no_unexplained_dead_kotlin_file():
    report = _scan()
    unexplained = sorted(set(report["unreferenced_files"]) - set(EXPLAINED_UNREFERENCED))
    assert unexplained == [], (
        "Kotlin files nothing references, with no recorded reason: "
        f"{unexplained}. Either wire them, delete them, or add them to "
        "EXPLAINED_UNREFERENCED with why."
    )


def test_no_unexplained_test_only_kotlin():
    report = _scan()
    paths = {path for path, _by in report["test_only"]}
    unexplained = sorted(paths - set(EXPLAINED_TEST_ONLY))
    assert unexplained == [], (
        "Kotlin reached only from tests, with no recorded reason: "
        f"{unexplained}. A test constructing a class is not a production caller."
    )


def test_every_explained_entry_still_describes_something_real():
    """An allowlist outliving what it excused is how one turns into a blanket.

    If a file is wired or deleted, its entry must go with it — otherwise the next dead file
    at that path inherits an excuse written for something else.
    """
    report = _scan()
    still_dead = set(report["unreferenced_files"]) | {p for p, _ in report["test_only"]}
    for path in list(EXPLAINED_UNREFERENCED) + list(EXPLAINED_TEST_ONLY):
        assert (ROOT / path).is_file(), f"{path} is allowlisted and does not exist"
        assert path in still_dead, (
            f"{path} is allowlisted as unreached and is now reached. Remove the entry."
        )


def test_the_test_only_entry_matches_the_component_ledger():
    """The scanner and the ledger must agree, or one of them is fiction.

    This is the reconciliation protocol rule 31 asks for, in the smallest form that can be
    automated: a file the scanner says nothing constructs must be recorded in the ledger as
    not constructed, with a disposition.
    """
    ledger = json.loads((ROOT / "evidence" / "van-system-audit" / "component_ledger.json").read_text())
    components = ledger["components"] if isinstance(ledger, dict) else ledger
    by_path = {c.get("path"): c for c in components}

    for path in EXPLAINED_TEST_ONLY:
        entry = by_path.get(path)
        assert entry is not None, f"{path} is unreached and absent from the component ledger"
        assert entry.get("disposition") in {"WIRE", "DELETE", "REPLACE"}, (
            f"{path} is unreached but the ledger dispositions it {entry.get('disposition')!r}"
        )
        assert not entry.get("terminal_state"), (
            f"{path} is unreached and the ledger claims a terminal state for it"
        )

# --- the scanner's own correctness, on synthetic input -------------------------
#
# Everything above asserts what the scanner says about the real tree, which cannot
# distinguish "the scanner is right" from "the tree happens to contain nothing it would get
# wrong". A mutation replacing the comment-stripping with `pass` survived every test above,
# because no file in this module names a dead symbol in its prose. That is luck, and the
# property it was hiding — a symbol mentioned in a KDoc is documentation, not a call site —
# is the one that decides whether a well-documented dead class looks alive.


def _scanner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kotlin_reachability", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_symbol_named_only_in_a_kdoc_is_not_a_call_site():
    strip = _scanner()._strip_noise
    source = """
/**
 * Replaces MissionRepository, which nothing constructs.
 */
class Something
"""
    assert "MissionRepository" not in strip(source)
    assert "Something" in strip(source), "the declaration itself was stripped"


def test_a_symbol_named_only_in_a_line_comment_is_not_a_call_site():
    strip = _scanner()._strip_noise
    assert "VanResourceEnvelope" not in strip("val x = 1 // see VanResourceEnvelope\n")


def test_a_symbol_named_only_in_a_string_is_not_a_call_site():
    """A class name in a log message or a route constant is not a construction."""
    strip = _scanner()._strip_noise
    assert "MissionRepository" not in strip('Log.d(TAG, "MissionRepository failed")')
    assert "MissionRepository" not in strip('''val s = """MissionRepository"""''')


def test_stripping_does_not_swallow_the_code_around_it():
    """Over-eager stripping would report everything as dead, which is its own failure."""
    strip = _scanner()._strip_noise
    source = 'val a = Alpha() // comment\nval b = Beta("text")\n'
    stripped = strip(source)
    assert "Alpha" in stripped and "Beta" in stripped


def test_declarations_are_found_through_the_modifiers_kotlin_allows():
    declarations = _scanner()._declarations
    source = """
internal class Alpha
private data class Beta(val n: Int)
sealed interface Gamma
@Composable
internal fun Delta() {}
enum class Epsilon { A }
object Zeta
typealias Eta = String
"""
    assert declarations(source) == {"Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta"}


def test_a_generic_function_declaration_is_still_found():
    """`fun <T> Name(...)` — a type parameter list sits between the keyword and the name.

    Without this, `fun <T> VanScreen(state: ScreenState<T>, ...)` never matched at all: the
    character after `fun\\s+` is `<`, not an identifier. `VanScreen` then silently dropped
    out of `declared[VanScreen.kt]`, and — because that file's other, non-generic symbols
    (`VanScreenSkeleton`, `VanErrorState`, ...) are called only from inside `VanScreen`
    itself, which is excluded as self-reference — the whole file read as unreferenced despite
    being called from three production screens.
    """
    declarations = _scanner()._declarations
    assert "VanScreen" in declarations("fun <T> VanScreen(state: ScreenState<T>) {}")
    assert "VanPanel" in declarations("@Composable\nfun VanPanel(modifier: Modifier) {}")
    assert declarations("fun <K, V> merge(a: K, b: V) {}") == {"merge"}
