"""Mutation harness.

The first version restored a mutated file with shutil.move, which preserves the backup's
mtime. That mtime was older than the .pyc written while the file was mutated, so Python
reused the *mutated* bytecode on the next run. A verdict reached that way is worthless: it
can report CAUGHT for a mutation that was never applied, or clean for one that was.

So the restore writes the original text back (fresh mtime) and every __pycache__ under the
tree is removed before each run.
"""
import pathlib, shutil, subprocess, sys


def _purge_bytecode(root: pathlib.Path) -> None:
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def run(mutations, tests, root=".", cwd=None, command=None):
    """`root` is what the mutation paths are relative to; `cwd` is where the suite runs.

    They differ for mutations outside backend/ — a workflow file, a Gradle script, Kotlin
    under android/ — whose tests still have to be invoked from the directory their runner
    expects. `command` replaces the pytest invocation for a suite pytest does not run; the
    Kotlin harness is a Gradle build.

    A mutation is `(path, old, new, why)`, or `(edits, why)` where `edits` is a list of
    `(path, old, new)` applied together. The compound form exists because an invariant held
    in two places — a guard clause and the table it guards — cannot be falsified by touching
    either one, and a single-edit mutation that survives for that reason says nothing about
    whether the invariant is tested.
    """
    root = pathlib.Path(root)
    verdicts = []
    for mutation in mutations:
        if len(mutation) == 2:
            edits, why = mutation
        else:
            path, old, new, why = mutation
            edits = [(path, old, new)]

        originals = {}
        try:
            for path, old, new in edits:
                f = root / path
                original = originals.setdefault(f, f.read_text())
                current = f.read_text()
                assert old in current, f"{path}: {old[:70]!r} not found"
                assert current.replace(old, new, 1) != current, f"{path}: mutation is a no-op"
                f.write_text(current.replace(old, new, 1))
            _purge_bytecode(root)
            result = subprocess.run(
                command or [sys.executable, "-m", "pytest", *tests, "-q"],
                capture_output=True, text=True, cwd=cwd,
            )
        finally:
            for f, text in originals.items():
                f.write_text(text)
            _purge_bytecode(root)
        caught = result.returncode != 0
        verdicts.append((caught, why))
        print(f"{'CAUGHT' if caught else '*** SURVIVED ***':18} {why}")
    survived = [why for caught, why in verdicts if not caught]
    print(f"\n{len(verdicts) - len(survived)}/{len(verdicts)} caught")
    return survived
