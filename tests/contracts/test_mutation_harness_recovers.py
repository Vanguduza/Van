"""The mutation harness must not be able to leave the tree mutated.

This is a test about the tooling rather than the product, and it exists because the failure
happened: a run was killed by a `timeout` mid-mutation, its `finally` never ran, and an
ownership check in `browser/interactive_api.py` was left replaced with `pass` in the working
tree. `git status` caught it before anything was committed. That is luck.

The consequence if it were not caught is specific and bad: a mutation is, by construction, a
deliberate removal of a security control, and the tree is committed from immediately after a
mutation run. So the harness journals what it has changed before it changes it, restores on
a signal, and recovers on the next start.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools" / "audit" / "mutation.py"


def test_the_journal_is_written_before_the_file_is_changed():
    """After the write is too late: the window is between mutating and being killed."""
    source = HARNESS.read_text()
    body = source[source.index("for path, old, new in edits:") :]
    body = body[: body.index("_purge_bytecode(root)")]
    journal_at = body.index("_write_journal(originals)")
    mutate_at = body.index("f.write_text(current.replace(old, new, 1))")
    assert journal_at < mutate_at, (
        "the journal is written after the mutation, which leaves exactly the window this "
        "is supposed to close"
    )


def test_a_killed_run_restores_what_it_mutated(tmp_path):
    """SIGTERM the harness mid-run and check the file it was holding came back."""
    victim = tmp_path / "victim.py"
    victim.write_text("GUARD = True\n")
    slow = tmp_path / "slow.py"
    slow.write_text("import time\ntime.sleep(60)\n")

    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(ROOT / "tools" / "audit")!r})
        from mutation import run
        run(
            [({str(victim.name)!r}, "GUARD = True", "GUARD = False", "kill me")],
            [],
            root={str(tmp_path)!r},
            command=[sys.executable, {str(slow)!r}],
        )
        """
    )
    runner = tmp_path / "runner.py"
    runner.write_text(script)

    process = subprocess.Popen([sys.executable, str(runner)])
    # Long enough for the mutation to have been applied and the slow command started.
    try:
        process.wait(timeout=6)
    except subprocess.TimeoutExpired:
        pass
    assert victim.read_text() == "GUARD = False\n", (
        "the mutation was never applied, so this test would pass for the wrong reason"
    )
    process.terminate()
    process.wait(timeout=20)

    assert victim.read_text() == "GUARD = True\n", (
        "a terminated run left the guard removed in the working tree"
    )


def test_a_leftover_journal_is_recovered_on_the_next_run(tmp_path, monkeypatch):
    """The second line of defence, for a kill the signal handler cannot catch (SIGKILL)."""
    sys.path.insert(0, str(ROOT / "tools" / "audit"))
    import mutation

    victim = tmp_path / "victim.py"
    victim.write_text("GUARD = False\n")  # as a killed run would have left it
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps({str(victim): "GUARD = True\n"}))
    monkeypatch.setattr(mutation, "JOURNAL", journal)

    restored = mutation.recover()

    assert restored == [str(victim)]
    assert victim.read_text() == "GUARD = True\n"
    assert not journal.exists()


def test_recovery_is_a_no_op_when_nothing_was_left_behind(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools" / "audit"))
    import mutation

    monkeypatch.setattr(mutation, "JOURNAL", tmp_path / "absent.json")
    assert mutation.recover() == []


def test_the_journal_is_not_committable():
    """A journal in the repository would mean a run's state outlived the run."""
    ignored = (ROOT / ".gitignore").read_text()
    assert "tools/audit/.mutation-journal.json" in ignored
