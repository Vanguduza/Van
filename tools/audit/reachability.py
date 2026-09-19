#!/usr/bin/env python3
"""Find Python symbols that exist and are never reached from production code.

The characteristic defect in this repository is not missing code. It is code that is
written, correct, sometimes tested, and never called — a class nobody constructs, a method
with no call site, a capability in a registry with no executor. A document says the feature
exists; a grep says the code exists; neither tells you it runs.

This answers the narrower question a grep cannot: **is this symbol referenced anywhere
outside its own definition and its own tests?**

It is deliberately conservative. It reports candidates, not verdicts:

- A symbol referenced only in tests is reported, because a test constructing a class is not
  a production caller — it is the pattern that makes isolated code look alive.
- Pydantic request/response models are excluded by default: FastAPI constructs them from the
  wire, so they have no textual call site and are not evidence of anything.
- Dynamic dispatch (getattr, registries keyed by string, entry points) is invisible to this
  and to every other static tool. A reported symbol may still be reached that way, which is
  why the output is a worklist for a human, not a finding.

Usage:
    python3 tools/audit/reachability.py                    # backend/van_gateway
    python3 tools/audit/reachability.py trading/vati
    python3 tools/audit/reachability.py --json             # machine-readable
    python3 tools/audit/reachability.py --include-models   # keep pydantic models
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Directories whose references do not count as production use. A symbol alive only here is
#: exactly the `TEST_ONLY` maturity class.
TEST_MARKERS = ("/tests/", "/test_", "conftest")

#: Base classes whose subclasses FastAPI or the framework constructs for us, so the absence
#: of a textual call site says nothing.
FRAMEWORK_BASES = {"BaseModel", "Enum", "IntEnum", "StrEnum", "Protocol", "TypedDict",
                   "Exception", "ValueError", "RuntimeError", "NamedTuple"}


@dataclass
class Symbol:
    name: str
    kind: str          # "class" | "function"
    path: str
    line: int
    bases: list[str] = field(default_factory=list)
    prod_refs: int = 0
    test_refs: int = 0

    @property
    def framework_constructed(self) -> bool:
        return bool(set(self.bases) & FRAMEWORK_BASES)

    def verdict(self) -> str:
        if self.prod_refs == 0 and self.test_refs == 0:
            return "NO_REFERENCE"
        if self.prod_refs == 0:
            return "TEST_ONLY"
        return "REFERENCED"


def is_test(path: Path) -> bool:
    text = str(path).replace("\\", "/")
    return any(marker in text for marker in TEST_MARKERS)


def base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return base_name(node.value)
    return ""


def collect(target: Path, scope: Path) -> tuple[dict[str, Symbol], dict[str, list[str]]]:
    """Definitions inside `target`; references counted across all of `scope`."""
    symbols: dict[str, Symbol] = {}
    for file in sorted(target.rglob("*.py")):
        if "__pycache__" in str(file) or is_test(file):
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = str(file.relative_to(ROOT))
        for node in tree.body:  # module level only: a nested helper is not the question
            if isinstance(node, ast.ClassDef):
                symbols[node.name] = Symbol(
                    node.name, "class", rel, node.lineno,
                    bases=[base_name(b) for b in node.bases],
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue  # private by convention; its module is the only caller by design
                symbols[node.name] = Symbol(node.name, "function", rel, node.lineno)

    where: dict[str, list[str]] = defaultdict(list)
    for file in sorted(scope.rglob("*.py")):
        if "__pycache__" in str(file):
            continue
        rel = str(file.relative_to(ROOT))
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        testish = is_test(file)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Name):
                names = [node.id]
            elif isinstance(node, ast.Attribute):
                names = [node.attr]
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # `from x import configure as configure_logging` is a real production
                # reference, and every later use is of the alias. Without this the symbol
                # reads as never used, which is a false positive that costs an auditor an
                # hour and, worse, trains them to distrust the tool.
                names = [alias.name.split(".")[-1] for alias in node.names]
            for name in names:
                if name in symbols:
                    _count(symbols[name], rel, node, testish, where)
    return symbols, where


def _count(sym: Symbol, rel: str, node: ast.AST, testish: bool,
           where: dict[str, list[str]]) -> None:
    """Record one reference, ignoring the definition site itself."""
    line = getattr(node, "lineno", -1)
    if rel == sym.path and line == sym.line:
        return
    if testish:
        sym.test_refs += 1
    else:
        sym.prod_refs += 1
        if len(where[sym.name]) < 4 and rel != sym.path:
            where[sym.name].append(f"{rel}:{line}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default="backend/van_gateway",
                    help="package to audit (default: backend/van_gateway)")
    ap.add_argument("--scope", default=None,
                    help="where to look for references (default: the target's parent)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-models", action="store_true",
                    help="keep pydantic models and enums, which the framework constructs")
    args = ap.parse_args()

    target = ROOT / args.target
    if not target.is_dir():
        print(f"no such package: {args.target}", file=sys.stderr)
        return 2
    scope = ROOT / args.scope if args.scope else target.parent

    symbols, where = collect(target, scope)
    suspects = [
        s for s in symbols.values()
        if s.verdict() != "REFERENCED"
        and (args.include_models or not s.framework_constructed)
    ]
    suspects.sort(key=lambda s: (s.verdict(), s.path, s.name))

    if args.json:
        print(json.dumps([{
            "name": s.name, "kind": s.kind, "path": s.path, "line": s.line,
            "verdict": s.verdict(), "production_references": s.prod_refs,
            "test_references": s.test_refs, "bases": s.bases,
        } for s in suspects], indent=2))
        return 0

    counted = len([s for s in symbols.values()
                   if args.include_models or not s.framework_constructed])
    print(f"{args.target}: {counted} module-level symbols considered, "
          f"{len(suspects)} with no production reference\n")
    for verdict in ("NO_REFERENCE", "TEST_ONLY"):
        rows = [s for s in suspects if s.verdict() == verdict]
        if not rows:
            continue
        note = ("defined and referenced nowhere at all"
                if verdict == "NO_REFERENCE"
                else "referenced only by its own tests")
        print(f"--- {verdict} ({len(rows)}) — {note} ---")
        for s in rows:
            tests = f"  [{s.test_refs} test refs]" if s.test_refs else ""
            print(f"  {s.kind:<8} {s.name:<44} {s.path}:{s.line}{tests}")
        print()
    print("Candidates, not verdicts: dynamic dispatch is invisible to static analysis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
