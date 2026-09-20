"""Mutation harness.

The first version restored a mutated file with shutil.move, which preserves the backup's
mtime. That mtime was older than the .pyc written while the file was mutated, so Python
reused the *mutated* bytecode on the next run. A verdict reached that way is worthless: it
can report CAUGHT for a mutation that was never applied, or clean for one that was.

So the restore writes the original text back (fresh mtime) and every __pycache__ under the
tree is removed before each run.
"""
import json, os, pathlib, shutil, signal, subprocess, sys

#: Where an in-progress run records what it has mutated.
#:
#: A run that is killed — a CI timeout, a Ctrl-C, the `timeout` command — does not
#: reach its `finally`, and leaves a source file mutated in the working tree. That
#: happened: a run was SIGTERM'd mid-mutation and left an ownership check in the
#: interactive browser router replaced with `pass`. It was found by `git status`
#: before anything was committed, which is luck and not a control.
#:
#: So the originals are written to disk before the first edit and removed after the
#: last, a signal handler restores on the way out, and a new run refuses to start
#: while the file exists.
JOURNAL = pathlib.Path(__file__).resolve().parent / ".mutation-journal.json"


def _purge_bytecode(root: pathlib.Path) -> None:
    for cache in root.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _write_journal(originals) -> None:
    JOURNAL.write_text(json.dumps({str(path): text for path, text in originals.items()}))


def _restore_from_journal() -> list[str]:
    """Put back anything a previous run left mutated. Returns what it restored."""
    if not JOURNAL.is_file():
        return []
    restored = []
    for path, text in json.loads(JOURNAL.read_text()).items():
        target = pathlib.Path(path)
        if target.is_file() and target.read_text() != text:
            target.write_text(text)
            restored.append(path)
    JOURNAL.unlink()
    return restored


def recover() -> list[str]:
    """Public entry point for the recovery, so a caller can report it."""
    restored = _restore_from_journal()
    if restored:
        _purge_bytecode(pathlib.Path("."))
    return restored


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
    stale = recover()
    if stale:
        print(f"recovered {len(stale)} file(s) a previous run left mutated: {stale}")
    verdicts = []
    for mutation in mutations:
        if len(mutation) == 2:
            edits, why = mutation
        else:
            path, old, new, why = mutation
            edits = [(path, old, new)]

        originals = {}

        def _emergency_restore(*_args):
            """Restore and re-raise the signal, so the kill still kills."""
            for path, text in originals.items():
                path.write_text(text)
            JOURNAL.unlink(missing_ok=True)
            os._exit(143)

        previous = {
            number: signal.signal(number, _emergency_restore)
            for number in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            for path, old, new in edits:
                f = root / path
                original = originals.setdefault(f, f.read_text())
                # Journalled before the write, not after: the window this closes is the one
                # between mutating a file and being killed.
                _write_journal(originals)
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
            JOURNAL.unlink(missing_ok=True)
            for number, handler in previous.items():
                signal.signal(number, handler)
            _purge_bytecode(root)
        caught = result.returncode != 0
        verdicts.append((caught, why))
        print(f"{'CAUGHT' if caught else '*** SURVIVED ***':18} {why}")
    survived = [why for caught, why in verdicts if not caught]
    print(f"\n{len(verdicts) - len(survived)}/{len(verdicts)} caught")
    return survived
