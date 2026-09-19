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


def run(mutations, tests, root=".", cwd=None):
    """`root` is what the mutation paths are relative to; `cwd` is where pytest runs.

    They differ for mutations outside backend/ — a workflow file or a Gradle script —
    whose tests still have to be invoked from the directory their conftest expects.
    """
    root = pathlib.Path(root)
    verdicts = []
    for path, old, new, why in mutations:
        f = root / path
        original = f.read_text()
        assert old in original, f"{path}: {old[:70]!r} not found"
        assert original.replace(old, new, 1) != original, f"{path}: mutation is a no-op"
        try:
            f.write_text(original.replace(old, new, 1))
            _purge_bytecode(root)
            result = subprocess.run(
                [sys.executable, "-m", "pytest", *tests, "-q"],
                capture_output=True, text=True, cwd=cwd,
            )
        finally:
            f.write_text(original)
            _purge_bytecode(root)
        caught = result.returncode != 0
        verdicts.append((caught, why))
        print(f"{'CAUGHT' if caught else '*** SURVIVED ***':18} {why}")
    survived = [why for caught, why in verdicts if not caught]
    print(f"\n{len(verdicts) - len(survived)}/{len(verdicts)} caught")
    return survived
