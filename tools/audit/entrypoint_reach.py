#!/usr/bin/env python3
"""Which gateway modules are reachable from an owner-facing entry point?

The blueprint's `CAUSALLY_INTEGRATED` class asks a question that neither a grep nor a
construction-site search answers: is there a path from something the owner can actually do
to this code? A class constructed inside a module that nothing imports is still unreachable
— it just fails a different check.

This walks the import graph from the real entry points (`app.py`, `orchestrator.py`,
`runtime_api.py`) and reports every module in the package that the walk never arrives at.

Import-level reachability is an over-approximation: an imported module may still hold a
class nobody constructs. So a module reported UNREACHABLE is definitely unreachable, while
one reported reachable merely *can* be reached. Use it to find the first kind.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = "van_gateway"
BASE = ROOT / "backend" / PKG
ENTRY = ["app.py", "orchestrator.py", "runtime_api.py"]


def module_of(path: Path) -> str:
    rel = path.relative_to(BASE).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([PKG] + parts)


def imports_of(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith(PKG):
                    found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                here = module_of(path).split(".")
                base = here[: len(here) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
                found.add(mod)
                for a in node.names:
                    found.add(f"{mod}.{a.name}")
            elif node.module and node.module.startswith(PKG):
                found.add(node.module)
                for a in node.names:
                    found.add(f"{node.module}.{a.name}")
    return found


def main() -> int:
    by_module = {module_of(p): p for p in BASE.rglob("*.py") if "__pycache__" not in str(p)}
    seen: set[str] = set()
    queue = [module_of(BASE / e) for e in ENTRY if (BASE / e).is_file()]
    while queue:
        mod = queue.pop()
        if mod in seen:
            continue
        seen.add(mod)
        path = by_module.get(mod)
        if path is None:
            continue
        for target in imports_of(path):
            # `from x.y import Z` yields both "x.y" and "x.y.Z"; only one is a module.
            for candidate in (target, target.rsplit(".", 1)[0]):
                if candidate in by_module and candidate not in seen:
                    queue.append(candidate)

    unreachable = sorted(set(by_module) - seen)
    unreachable = [m for m in unreachable if not m.endswith("__init__") and m != PKG]
    print(f"{len(by_module)} modules, {len(seen)} reachable from {', '.join(ENTRY)}, "
          f"{len(unreachable)} never imported\n")
    for m in unreachable:
        print(f"  {m}")
    if unreachable:
        print("\nAn unreachable module is definitely dead. A reachable one merely can be reached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
