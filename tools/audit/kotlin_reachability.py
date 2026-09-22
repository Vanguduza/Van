#!/usr/bin/env python3
"""Find Kotlin files and symbols in the Android app that nothing production reaches.

`tools/audit/reachability.py` answers this for the gateway. The Android side had no
equivalent, and that is where this programme's most expensive defect lived: `P0-AND-012`,
four Kotlin compile errors on a branch nobody could build, hidden because the Android Gradle
Plugin cannot be fetched in this container and CI did not run here. A compiler would have
found those. It would not have found a Composable nothing renders or a policy object nothing
consults, which is the class this exists for.

The Android question differs from the Python one in a way worth stating, because it changes
what an honest answer looks like. A gateway module is reached from `app.py` or it is dead.
An Android class can be reached from the manifest, from a Compose call, from a DI graph,
from a reflective service binding, or from nothing at all — and only the last is a defect.
So reachability here is computed from the manifest's declared components outwards, and
everything the sweep cannot explain is reported as a **candidate**, never as a verdict.

What it reports:

- **unreferenced files** — a file whose declared symbols appear in no other production file.
  A screen nobody navigates to, a policy nobody asks.
- **test-only symbols** — declared in production, referenced only from
  `android/verification/src/test`. The `TEST_ONLY` maturity class, which this programme has
  repeatedly found masquerading as integration. I have produced one myself.
- **unreachable from the manifest** — files not transitively reachable from any declared
  Activity, Service, Receiver, Provider or the Application class. This is the weakest of the
  three signals and the most likely to be wrong, because Compose and reflection are both
  invisible here; it is printed last and labelled.

What it deliberately does not do: parse Kotlin. A real parser would be better and is a much
larger thing to get right, and a half-parser that silently mis-handles a generic signature
would produce confident wrong answers, which is worse than obviously-approximate ones. This
is a textual sweep with declared limits.

Usage:
    python3 tools/audit/kotlin_reachability.py
    python3 tools/audit/kotlin_reachability.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# The scanner is shared with the compile gate: see tools/audit/kotlin_source.py for
# why it is one implementation rather than two.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kotlin_source import strip_noise  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main" / "java"
MANIFEST = ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
APP_TESTS = ROOT / "android" / "app" / "src" / "test"
HARNESS_TESTS = ROOT / "android" / "verification" / "src" / "test"

#: Top-level declarations. Kotlin allows `internal`, `private`, `public`, `open`, `abstract`,
#: `sealed`, `data`, `enum`, `annotation`, `value`, `inline`, `suspend` in front, in orders
#: the language permits and people use inconsistently, so the prefix is matched loosely and
#: the keyword exactly.
DECLARATION = re.compile(
    r"^(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|internal|private|protected|open|abstract|sealed|data|value|inline|"
    r"expect|actual|external)\s+)*"
    r"(?:(?:enum|annotation|companion)\s+)?"
    r"(class|object|interface|fun|val|var|typealias)\s+"
    # `fun <T> Name(...)` / `fun <T, U> Name(...)` — a generic function's type parameter
    # list sits between the keyword and the name. Without this, `fun <T> VanScreen(` never
    # matches at all: the next character after `fun\s+` is `<`, not an identifier, so the
    # whole declaration — and every symbol this file also declares — silently drops out of
    # the reachability graph, which is a false "nothing calls this" on a component that is
    # in fact called from three screens (`VanScreen.kt`, found on this scanner's first run
    # over the DNA §4 rebuild).
    r"(?:<[^<>]*>\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)

#: A Composable is a function, but one whose only caller may be another Composable in a file
#: this sweep also cannot explain. Tracked so the report can say so rather than listing a
#: whole screen as dead.
COMPOSABLE = re.compile(r"@Composable\s*(?:\n\s*)*(?:(?:private|internal|public)\s+)?fun\s+([A-Za-z_]\w*)")

#: Components Android itself instantiates. Nothing in the source calls their constructors.
#:
#: Scoped to the elements that declare a class. A bare `android:name` sweep also matches
#: <uses-permission>, <action> and <category>, which put ACCESS_NETWORK_STATE, MAIN and
#: LAUNCHER into the entry-point set — harmless-looking until a class shares a name with one
#: of them and is silently treated as platform-instantiated, which is a scanner that hides
#: exactly what it exists to find.
MANIFEST_COMPONENT = re.compile(
    r"<(?:activity|activity-alias|service|receiver|provider|application)\b[^>]*?"
    r'android:name="\.?([A-Za-z0-9_.]+)"',
    re.DOTALL,
)


def _kotlin_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.kt")) if base.is_dir() else []


_strip_noise = strip_noise


def _declarations(text: str) -> set[str]:
    return {match.group(2) for match in DECLARATION.finditer(text)}


def _fqcn(path: Path, text: str) -> str:
    package = re.search(r"^package\s+([\w.]+)", text, re.MULTILINE)
    return f"{package.group(1)}.{path.stem}" if package else path.stem


def scan() -> dict:
    production = {path: _strip_noise(path.read_text(encoding="utf-8")) for path in _kotlin_files(APP)}
    tests = {
        path: _strip_noise(path.read_text(encoding="utf-8"))
        for base in (APP_TESTS, HARNESS_TESTS)
        for path in _kotlin_files(base)
    }

    declared: dict[Path, set[str]] = {path: _declarations(text) for path, text in production.items()}
    composables: dict[Path, set[str]] = {
        path: {m.group(1) for m in COMPOSABLE.finditer(text)} for path, text in production.items()
    }

    manifest = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""
    entry_names = {name.rsplit(".", 1)[-1] for name in MANIFEST_COMPONENT.findall(manifest)}

    # ---- references ---------------------------------------------------------
    def referenced_in(symbol: str, sources: dict[Path, str], exclude: Path) -> list[Path]:
        pattern = re.compile(rf"\b{re.escape(symbol)}\b")
        return [p for p, text in sources.items() if p != exclude and pattern.search(text)]

    unreferenced_files = []
    test_only = []
    for path, symbols in declared.items():
        if not symbols:
            continue
        stem = path.stem
        # A file whose name is a manifest component is instantiated by the platform.
        if stem in entry_names or symbols & entry_names:
            continue
        reached_by = set()
        reached_by_tests = set()
        for symbol in symbols:
            reached_by.update(referenced_in(symbol, production, path))
            reached_by_tests.update(referenced_in(symbol, tests, path))
        if not reached_by and not reached_by_tests:
            unreferenced_files.append(path)
        elif not reached_by and reached_by_tests:
            test_only.append((path, sorted(s.name for s in reached_by_tests)[:3]))

    # ---- manifest reachability ----------------------------------------------
    # Breadth-first from the declared components over "this file names a symbol that file
    # declares". Compose and DI make this approximate in the direction of over-reporting
    # unreachability, which is why it is printed last and labelled.
    owner_of: dict[str, set[Path]] = defaultdict(set)
    for path, symbols in declared.items():
        for symbol in symbols:
            owner_of[symbol].add(path)

    frontier = {p for p in production if p.stem in entry_names or declared[p] & entry_names}
    reachable = set(frontier)
    while frontier:
        nxt = set()
        for path in frontier:
            text = production[path]
            for symbol, owners in owner_of.items():
                if owners <= reachable:
                    continue
                if re.search(rf"\b{re.escape(symbol)}\b", text):
                    for owner in owners - reachable:
                        nxt.add(owner)
        reachable |= nxt
        frontier = nxt

    unreachable = sorted(set(production) - reachable)

    return {
        "files": len(production),
        "entry_points": sorted(entry_names),
        "unreferenced_files": sorted(str(p.relative_to(ROOT)) for p in unreferenced_files),
        "test_only": sorted((str(p.relative_to(ROOT)), by) for p, by in test_only),
        "unreachable_from_manifest": [str(p.relative_to(ROOT)) for p in unreachable],
        "composable_files": sorted(
            str(p.relative_to(ROOT)) for p, names in composables.items() if names
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = scan()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"{report['files']} Kotlin files in the app module")
    print(f"{len(report['entry_points'])} manifest components: {', '.join(report['entry_points'])}")

    print("\n-- declared and referenced by nothing, production or test ----------")
    for path in report["unreferenced_files"] or ["  (none)"]:
        print(f"  {path}")

    print("\n-- referenced only from tests (the TEST_ONLY class) ----------------")
    for path, by in report["test_only"] or [("  (none)", [])]:
        print(f"  {path}  {by}")

    print("\n-- not reachable from a manifest component -------------------------")
    print("   Weakest signal here: Compose call graphs and reflective bindings are invisible")
    print("   to a textual sweep, so this over-reports. A worklist, not a verdict.")
    for path in report["unreachable_from_manifest"] or ["  (none)"]:
        print(f"  {path}")

    print("\nCandidates, not verdicts. Kotlin has reflection, Compose and DI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
