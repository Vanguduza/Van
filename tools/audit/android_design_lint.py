#!/usr/bin/env python3
"""VAN Android design-system lint (docs/design/VAN_PRODUCT_DESIGN_DNA.md).

Four mechanical rules a screen can violate without anyone noticing until a design review
catches it by eye — which is how the app accumulated raw hex literals and bare `N.sp` sizes
one call site at a time. Each rule is a fact about where a construct is allowed to live, not
a style opinion, so it is checked the same way `test_android_compiles_at_all.py` checks a
visibility rule: by parsing the source, not by looking at a screenshot.

  a. `Color(0x...)` literals outside `com/dial/van/design/` and `com/dial/van/visual/` — a
     screen paints with `VanColorTokens`, not a colour it invented on the spot. `visual/` is
     exempt because it *is* the palette (`VanPalette`, `VanGlassTokens`) the design tokens are
     built from.
  b. `fontSize = N.sp` with `N < 12`, anywhere at all — DNA §2: "Minimum text size 12sp
     anywhere." No exemption for `design/` itself: a token file that defines an 11sp style is
     exactly as wrong as a screen that hardcodes one.
  c. `fontSize = N.sp` literals outside `design/`, at any size — DNA §2's type tokens
     (`VanTypeTokens.display/title/.../label`) exist so a screen states an intent ("this is a
     label") rather than a number. `design/` is exempt because that is where the tokens
     themselves are defined.
  d. `Card(`/`ElevatedCard(` outside `design/` — DNA §1: "Panels are acrylic... No glass on
     cards." A screen reaches for `VanPanel`, not Material's own card, so every card in the
     app goes through the one place the acrylic-vs-glass policy is enforced.

Bare word counts, not "line contains a token": `strip_noise` (shared with
`test_android_compiles_at_all.py` and the reachability gate) removes comments and string
literals first, so a KDoc paragraph that *mentions* `Color(0x...)` — such as this file's own
docstring, or a component's doc comment explaining what NOT to do — is not itself a violation.

Ratcheting: pass `--baseline PATH` to compare against a checked-in violation count per
rule/file. A file whose count is at or below its baseline passes; a file with a higher count,
or a violation in a file/rule pair the baseline does not mention at all, fails. This is how a
codebase with existing violations adopts the lint without a single all-or-nothing fix: today's
count is the floor, and every subsequent change may only lower it, never raise it — checked by
`tests/contracts/test_android_design_lint.py`, which also fails if the committed baseline
itself has grown against what is on disk (see that file for the exact invariant).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_MAIN = ROOT / "android" / "app" / "src" / "main" / "java"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kotlin_source import strip_noise  # noqa: E402

DESIGN_PREFIX = "com/dial/van/design/"
VISUAL_PREFIX = "com/dial/van/visual/"

#: Rule id -> one-line description, printed once in the table header and used as the JSON key.
RULES: dict[str, str] = {
    "raw_color_literal": "Color(0x...) outside design/ and visual/",
    "font_size_under_12sp": "fontSize = N.sp with N < 12, anywhere",
    "font_size_literal_outside_design": "fontSize = N.sp literal outside design/",
    "material_card_outside_design": "Card(/ElevatedCard( outside design/",
}

_COLOR_LITERAL_RE = re.compile(r"\bColor\(\s*0[xX][0-9A-Fa-f]")
_FONT_SIZE_RE = re.compile(r"fontSize\s*=\s*(-?\d+(?:\.\d+)?)\s*\.sp\b")
_CARD_RE = re.compile(r"\b(?:Elevated)?Card\(")

#: rule -> {relative path: count}, zero counts omitted.
ScanResult = dict[str, dict[str, int]]


def _relpath(path: Path) -> str:
    return path.relative_to(APP_MAIN).as_posix()


def _kotlin_files() -> list[Path]:
    return sorted(APP_MAIN.rglob("*.kt"))


def scan_file(path: Path) -> dict[str, int]:
    """This file's violation count per rule. Zero for a rule this file has none of."""
    rel = _relpath(path)
    text = strip_noise(path.read_text(encoding="utf-8"))
    counts = {rule: 0 for rule in RULES}

    in_design = rel.startswith(DESIGN_PREFIX)
    in_visual = rel.startswith(VISUAL_PREFIX)

    if not (in_design or in_visual):
        counts["raw_color_literal"] = len(_COLOR_LITERAL_RE.findall(text))

    for match in _FONT_SIZE_RE.finditer(text):
        if float(match.group(1)) < 12:
            counts["font_size_under_12sp"] += 1

    if not in_design:
        counts["font_size_literal_outside_design"] = len(_FONT_SIZE_RE.findall(text))
        counts["material_card_outside_design"] = len(_CARD_RE.findall(text))

    return counts


def scan_tree() -> ScanResult:
    results: ScanResult = {rule: {} for rule in RULES}
    for path in _kotlin_files():
        rel = _relpath(path)
        for rule, count in scan_file(path).items():
            if count > 0:
                results[rule][rel] = count
    return results


def total_violations(results: ScanResult) -> int:
    return sum(sum(files.values()) for files in results.values())


def load_baseline(path: Path) -> ScanResult:
    if not path.exists():
        return {rule: {} for rule in RULES}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {rule: dict(raw.get(rule, {})) for rule in RULES}


def write_baseline(path: Path, results: ScanResult) -> None:
    path.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def diff_against_baseline(
    results: ScanResult,
    baseline: ScanResult,
) -> list[tuple[str, str, int, int]]:
    """`(rule, path, baseline_count, current_count)` for every pair whose count rose.

    A pair the baseline never mentions has an implicit baseline of 0, so any violation
    there — a brand-new file, or a rule a file previously had none of — is "grown from 0"
    and reported the same way an existing pair's count going up is: there is no separate
    "unknown violation" category, because unknown-but-present is exactly what a regression
    looks like the first time it happens.
    """
    problems: list[tuple[str, str, int, int]] = []
    for rule in RULES:
        baseline_files = baseline.get(rule, {})
        for rel, count in sorted(results[rule].items()):
            base_count = baseline_files.get(rel, 0)
            if count > base_count:
                problems.append((rule, rel, base_count, count))
    return problems


def format_table(results: ScanResult) -> str:
    rows: list[tuple[str, str, int]] = []
    for rule in RULES:
        for rel, count in sorted(results[rule].items()):
            rows.append((rule, rel, count))
    if not rows:
        return "No design-lint violations."

    rule_width = max(len(r[0]) for r in rows)
    path_width = max(len(r[1]) for r in rows)
    lines = [f"{'rule':<{rule_width}}  {'file':<{path_width}}  count"]
    lines.append("-" * (rule_width + path_width + 9))
    for rule, rel, count in rows:
        lines.append(f"{rule:<{rule_width}}  {rel:<{path_width}}  {count}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline JSON to ratchet against. Without it, any violation at all fails.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write today's violations to --baseline instead of checking against it.",
    )
    args = parser.parse_args(argv)

    results = scan_tree()

    if args.write_baseline:
        if args.baseline is None:
            print("error: --write-baseline requires --baseline PATH", file=sys.stderr)
            return 2
        write_baseline(args.baseline, results)
        print(f"Wrote baseline with {total_violations(results)} violation(s) to {args.baseline}")
        return 0

    print(format_table(results))
    pairs = sum(len(files) for files in results.values())
    print(f"\n{total_violations(results)} violation(s) across {pairs} file/rule pair(s).")

    if args.baseline is None:
        return 1 if total_violations(results) > 0 else 0

    baseline = load_baseline(args.baseline)
    problems = diff_against_baseline(results, baseline)
    if problems:
        print(f"\nNEW OR GROWN violations, not covered by {args.baseline}:")
        for rule, rel, base_count, count in problems:
            print(f"  {rule}: {rel} — baseline {base_count}, now {count}")
        return 1

    print(f"\nAll violations are covered by the baseline ({args.baseline}); no new or grown violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
