"""docs/design/VAN_PRODUCT_DESIGN_DNA.md §2/§7 (Gate V2) — the design-system lint, enforced.

`tools/audit/android_design_lint.py` finds raw colour literals, bare `N.sp` sizes and
Material `Card`/`ElevatedCard` usage outside `com/dial/van/design/`. The app had 464 of these
on the day the lint was written, spread across every screen package — fixing them all before
the lint could exist would have blocked every other worker's PR on a rewrite none of them
asked for. `tools/audit/android_design_lint_baseline.json` records that starting count per
rule and file, and the tool passes as long as nothing exceeds its own baseline entry: a
screen migrating onto `VanPanel`/`VanColorTokens` lowers its own numbers over time, and a
screen regressing — someone reaching for `Color(0x...)` again — is caught the same run.

This is the one-way ratchet, checked two ways:

1. The lint, run exactly as CI runs it, passes against the checked-in baseline right now —
   the same invocation `tools/audit/android_design_lint.py`'s own module docstring and the
   worker's task both name.
2. `diff_against_baseline` itself is exercised directly against synthetic before/after counts,
   so the ratchet rule is proven independently of whatever the app's current violation count
   happens to be — a file whose count *fell* is fine, stayed the same is fine, and *rose*
   (including from an entry the baseline never mentioned, an implicit 0) is caught.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINT_SCRIPT = ROOT / "tools" / "audit" / "android_design_lint.py"
BASELINE = ROOT / "tools" / "audit" / "android_design_lint_baseline.json"

sys.path.insert(0, str(ROOT / "tools" / "audit"))
import android_design_lint as lint  # noqa: E402


def test_the_lint_script_and_its_baseline_exist():
    assert LINT_SCRIPT.is_file(), "tools/audit/android_design_lint.py is missing"
    assert BASELINE.is_file(), "tools/audit/android_design_lint_baseline.json is missing"


def test_the_lint_passes_against_the_checked_in_baseline():
    """The exact command the worker's task and CI both run."""
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "--baseline", str(BASELINE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"android_design_lint.py --baseline found new or grown violations:\n{result.stdout}\n{result.stderr}"
    )


def test_the_baseline_is_valid_json_shaped_like_the_lint_expects():
    baseline = lint.load_baseline(BASELINE)
    assert set(baseline.keys()) == set(lint.RULES.keys()), (
        "the baseline's rule keys have drifted from android_design_lint.py's RULES"
    )
    for rule, files in baseline.items():
        for rel, count in files.items():
            assert isinstance(rel, str) and rel, f"{rule} has a blank path"
            assert isinstance(count, int) and count > 0, f"{rule}/{rel} baseline count is not a positive int"


def test_the_current_tree_never_exceeds_its_own_baseline_entry():
    """Same invariant as the CLI's exit code, asserted per rule/file for a legible failure."""
    results = lint.scan_tree()
    baseline = lint.load_baseline(BASELINE)
    offenders = []
    for rule in lint.RULES:
        for rel, count in results[rule].items():
            base_count = baseline.get(rule, {}).get(rel, 0)
            if count > base_count:
                offenders.append(f"{rule}: {rel} baseline={base_count} current={count}")
    assert not offenders, "violations exceed the committed baseline:\n" + "\n".join(offenders)


# ---- the ratchet rule itself, proven independently of the app's current violation count -----

def test_diff_reports_nothing_when_current_matches_baseline():
    baseline = {"raw_color_literal": {"Foo.kt": 3}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    current = {"raw_color_literal": {"Foo.kt": 3}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    assert lint.diff_against_baseline(current, baseline) == []


def test_diff_reports_nothing_when_a_file_improves():
    baseline = {"raw_color_literal": {"Foo.kt": 5}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    current = {"raw_color_literal": {"Foo.kt": 2}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    assert lint.diff_against_baseline(current, baseline) == []


def test_diff_catches_a_file_that_grew_past_its_own_baseline():
    baseline = {"raw_color_literal": {"Foo.kt": 3}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    current = {"raw_color_literal": {"Foo.kt": 4}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    problems = lint.diff_against_baseline(current, baseline)
    assert problems == [("raw_color_literal", "Foo.kt", 3, 4)]


def test_diff_catches_a_violation_in_a_file_the_baseline_never_mentioned():
    """An implicit baseline of 0 — the file was clean when the baseline was written."""
    baseline = {"raw_color_literal": {}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    current = {"raw_color_literal": {"NewFile.kt": 1}, "font_size_under_12sp": {}, "font_size_literal_outside_design": {}, "material_card_outside_design": {}}
    problems = lint.diff_against_baseline(current, baseline)
    assert problems == [("raw_color_literal", "NewFile.kt", 0, 1)]


def test_scan_file_does_not_flag_a_violation_only_mentioned_in_a_doc_comment(tmp_path):
    """A KDoc paragraph explaining what *not* to do must not itself read as a violation."""
    fake_app_main = tmp_path / "java"
    package_dir = fake_app_main / "com" / "dial" / "van" / "command"
    package_dir.mkdir(parents=True)
    kt_file = package_dir / "Example.kt"
    kt_file.write_text(
        "package com.dial.van.command\n\n"
        "/**\n"
        " * Screens must not write `Color(0xFF00E5FF)` or `fontSize = 9.sp` — use the\n"
        " * design tokens instead. A `Card(` here would also be wrong.\n"
        " */\n"
        "fun example() {}\n",
        encoding="utf-8",
    )

    original_app_main = lint.APP_MAIN
    try:
        lint.APP_MAIN = fake_app_main
        counts = lint.scan_file(kt_file)
    finally:
        lint.APP_MAIN = original_app_main

    assert counts == {rule: 0 for rule in lint.RULES}, (
        f"a doc-comment example was counted as a real violation: {counts}"
    )
