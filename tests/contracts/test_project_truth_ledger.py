"""Owner decision 2026-09-30: "enforce van's ledger".

`tools/ci/project_truth_ledger.py` is the only thing that reads LOCAL_CHANGE_LEDGER.jsonl, so
each failure it exists to catch is induced here in a throwaway repository and watched to
fail: a commit with no row, a row whose digest was altered, a file no authorization covers,
an authorization that does not exist or was revoked, an edited row or record. Review I6 showed
the first version passed a forged row citing a non-reusable record, a PR authorizing itself,
an authorization record edited in a committed change, a `*` glob crossing directories, a
truncated "(append-only)" file, a PR moving its own baseline or widening its own authority
set, and a PR running its own checker; each of those is induced here too, as a committed
change, and `tests/contracts/ledger_guard_mutations.py` deletes each guard in turn and shows a test
here fails. The passing paths (hook row binding to its commit, merges, supersession, the
intake-first bootstrap) are checked the same way, and the real branch is verified at HEAD.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# tests/contracts/ledger_guard_mutations.py points this at a copy with one guard deleted.
CHECKER = Path(os.environ.get("PROJECT_TRUTH_LEDGER_CHECKER_UNDER_TEST") or ROOT / "tools" / "ci" / "project_truth_ledger.py")
LEDGER = "docs/project-state/LOCAL_CHANGE_LEDGER.jsonl"
AUTH_DIR = "docs/project-state/authorizations"
CONFIG = "registries/project_truth_ledger_baselines.json"

_spec = importlib.util.spec_from_file_location("project_truth_ledger", CHECKER)
ptl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ptl)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True).stdout.strip()


def run(root: Path, *args: str, capsys=None) -> tuple[int, str]:
    rc = ptl.main(["--repo", str(root), *args])
    out = ""
    if capsys is not None:
        captured = capsys.readouterr()
        out = captured.out + captured.err
    return rc, out


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def auth_record(aid: str, paths: list[str], **extra) -> str:
    rec = {"schema_version": 1, "authorization_id": aid, "project": "van", "authority": "OWNER_DERIVED",
           "authorized_paths": paths, "reusable": False, "revoked": False}
    rec.update(extra)
    return json.dumps(rec, indent=2) + "\n"


def binding_record(bid: str, binds: dict[str, list[str]], **extra) -> str:
    rec = {"schema_version": 1, "authorization_id": bid, "record_kind": "commit_scope_binding",
           "authority": "OWNER_DERIVED", "binds": {k: {"commits": v} for k, v in binds.items()}}
    rec.update(extra)
    return json.dumps(rec, indent=2) + "\n"


def commit(root: Path, msg: str) -> str:
    git(root, "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path):
    root = tmp_path / "van"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    write(root, "README.md", "van\n")
    write(root, LEDGER, "")
    git(root, "add", ".")
    commit(root, "baseline")
    return root


def baseline(root: Path) -> str:
    return git(root, "rev-list", "--max-parents=0", "HEAD")


def reusable_commit(root: Path, aid: str, files: dict[str, str], msg: str) -> str:
    """A commit made the way the pre-commit hook makes it, under a reusable record it adds."""
    write(root, f"{AUTH_DIR}/{aid}.json", auth_record(aid, [*files, f"{AUTH_DIR}/{aid}.json"], reusable=True))
    for rel, text in files.items():
        write(root, rel, text)
    git(root, "add", ".")
    assert ptl.main(["--repo", str(root), "record", "--stage"]) == 0
    return commit(root, msg)


def unrecorded_commit(root: Path, files: dict[str, str | None], msg: str) -> str:
    for rel, text in files.items():
        if text is None:
            git(root, "rm", "-q", rel)
        else:
            write(root, rel, text)
            git(root, "add", rel)
    return commit(root, msg)


def forge_row(root: Path, sha: str, ids: list[str]) -> None:
    r = ptl.Repo(root)
    row = {"schema_version": 2, "kind": "integrator-commit-diff", "commit_sha": sha, "parent_sha": r.parents(sha)[0],
           "commit_diff_sha256": ptl.commit_digest(r, sha), "authorization_ids": ids}
    with (root / LEDGER).open("a") as fh:
        fh.write(ptl.serialize(row) + "\n")


def commit_ledger(root: Path, msg: str = "ledger rows") -> str:
    git(root, "add", LEDGER)
    return commit(root, msg)


def intake(root: Path, records: dict[str, str], msg: str = "intake") -> str:
    """Commit that only adds authorization record files, with its row (as the hook writes it)."""
    for aid, text in records.items():
        write(root, f"{AUTH_DIR}/{aid}.json", text)
    git(root, "add", ".")
    rc = ptl.main(["--repo", str(root), "record", "--stage"])
    assert rc == 0
    return commit(root, msg)


def scoped_authorization(root: Path, aid: str, paths: list[str], shas: list[str], expect_covered: bool = True) -> str:
    """Retroactive owner authority for existing commits: intake the record, then add their rows."""
    sha = intake(root, {aid: auth_record(aid, paths, commit_scope={"commits": shas})}, f"intake {aid}")
    for s in shas:
        if expect_covered:
            assert ptl.main(["--repo", str(root), "record", "--commit", s, "--auth", aid]) == 0
        else:  # record refuses these; forge the rows a careless integrator could write
            forge_row(root, s, [aid])
    commit_ledger(root)
    return sha


def verify(root: Path, capsys, *extra: str) -> tuple[int, str]:
    return run(root, "verify", "--baseline", baseline(root), *extra, capsys=capsys)


def set_config(root: Path, lineages: list[dict], **extra) -> None:
    write(root, CONFIG, json.dumps({"lineages": lineages, **extra}, indent=2))


# ------------------------------------------------------------------ passing paths

def test_a_hook_row_binds_to_the_commit_it_becomes(repo, capsys):
    sha = reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n", "img.bin": "\x00\x01"}, "one")
    rows = [json.loads(x) for x in (repo / LEDGER).read_text().splitlines()]
    assert len(rows) == 1 and "commit_sha" not in rows[0]
    assert rows[0]["parent_sha"] == baseline(repo)
    assert rows[0]["commit_diff_sha256"] == ptl.commit_digest(ptl.Repo(repo), sha)
    assert rows[0]["authorization_ids"] == ["auth-test-one"]
    rc, out = verify(repo, capsys)
    assert rc == 0, out
    assert "GREEN" in out


def test_a_ledger_only_commit_needs_no_row(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    with (repo / LEDGER).open("a") as fh:
        fh.write(json.dumps({"kind": "note"}) + "\n")
    commit_ledger(repo, "ledger only")
    rc, out = verify(repo, capsys)
    assert rc == 0, out


def test_a_scoped_record_covers_exactly_the_commits_it_names(repo, capsys):
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "made before the owner's record")
    b = unrecorded_commit(repo, {"src/a.py": "a = 2\n"}, "also before it")
    rc, out = verify(repo, capsys)
    assert rc == 1 and f"MISSING_ROW {a}" in out
    # The owner's authority arrives afterwards as an intake commit naming the two commits.
    ik = scoped_authorization(repo, "auth-test-later", ["src/a.py"], [a, b])
    rows = [json.loads(x) for x in (repo / LEDGER).read_text().splitlines()]
    assert rows[0]["kind"] == "authorization-intake" and rows[0]["authorization_ids"] == ["auth-test-later"]
    assert {r.get("commit_sha") for r in rows[1:]} == {a, b}
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 0, out
    assert ik


def test_an_intake_commit_needs_a_row(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-x.json", auth_record("auth-test-x", ["src/x.py"], reusable=True))
    git(repo, "add", ".")
    sha = commit(repo, "record with no row")
    rc, out = verify(repo, capsys)
    assert rc == 1 and f"MISSING_ROW {sha}" in out


# ------------------------------------------------------------------ induced failures

def test_a_commit_with_no_row_fails(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    sha = unrecorded_commit(repo, {"src/a.py": "a = 2\n"}, "no hook")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"MISSING_ROW {sha}" in out


def test_a_tampered_digest_fails(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    sha = unrecorded_commit(repo, {"src/a.py": "a = 2\n"}, "recorded afterwards")
    assert run(repo, "record", "--commit", sha, "--auth", "auth-test-one", capsys=capsys)[0] == 0
    assert verify(repo, capsys)[0] == 0
    text = (repo / LEDGER).read_text()
    row = json.loads(text.splitlines()[-1])
    assert row["commit_sha"] == sha
    row["commit_diff_sha256"] = "0" * 64
    (repo / LEDGER).write_text("\n".join(text.splitlines()[:-1] + [json.dumps(row)]) + "\n")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"DIGEST_MISMATCH {sha}" in out


def test_a_tampered_hook_row_no_longer_binds(repo, capsys):
    sha = reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    text = (repo / LEDGER).read_text()
    (repo / LEDGER).write_text(text.replace(json.loads(text)["commit_diff_sha256"], "f" * 64))
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"MISSING_ROW {sha}" in out


def test_an_uncovered_file_fails_and_record_refuses_it(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-one.json", auth_record("auth-test-one", ["src/a.py", f"{AUTH_DIR}/auth-test-one.json"], reusable=True))
    write(repo, "src/a.py", "a = 1\n")
    write(repo, "src/b.py", "b = 1\n")
    git(repo, "add", ".")
    before = (repo / LEDGER).read_text()
    rc, out = run(repo, "record", "--stage", capsys=capsys)
    assert rc == 3 and "src/b.py" in out
    assert (repo / LEDGER).read_text() == before, "a refused record must write nothing"
    assert run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)[0] == 0
    sha = commit(repo, "b is not authorized")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"UNCOVERED_FILES {sha}: 1 file(s)" in out and "src/b.py" in out


def test_an_unknown_authorization_fails(repo, capsys):
    sha = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    forge_row(repo, sha, ["auth-does-not-exist"])
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"UNKNOWN_AUTHORIZATION {sha}" in out
    assert f"UNCOVERED_FILES {sha}" in out


def test_a_revoked_authorization_fails(repo, capsys):
    sha = reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    assert verify(repo, capsys)[0] == 0
    # Revocation is itself append-only: a later record names the one it withdraws.
    intake(repo, {"auth-test-revoke2": auth_record("auth-test-revoke2", ["nothing"], revokes=["auth-test-one"])}, "revoke one")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"REVOKED_AUTHORIZATION {sha}: auth-test-one: revoked by auth-test-revoke2" in out


def test_a_record_marked_revoked_fails(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-dead.json", auth_record("auth-test-dead", ["src/a.py", f"{AUTH_DIR}/auth-test-dead.json"], revoked=True, reusable=True))
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    rc, out = run(repo, "record", "--stage", "--auth", "auth-test-dead", capsys=capsys)
    assert rc == 2 and "REVOKED_AUTHORIZATION" in out
    sha = commit(repo, "one")
    forge_row(repo, sha, ["auth-test-dead"])
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"REVOKED_AUTHORIZATION {sha}: auth-test-dead: record says revoked" in out


def test_a_no_authority_record_fails(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-none.json", auth_record("auth-test-none", ["src/a.py", f"{AUTH_DIR}/auth-test-none.json"], authority="NO_AUTHORITY", reusable=True))
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)[0] == 0
    sha = commit(repo, "one")
    rc, out = verify(repo, capsys)
    assert rc == 1 and f"UNCOVERED_FILES {sha}" in out


def test_the_config_cannot_add_an_authority_class(repo, capsys):
    """I6 case 9: allowed_authorities gained AGENT_SELF. The list can only narrow the owner classes."""
    set_config(repo, [{"id": "t", "baseline_sha": baseline(repo)}], allowed_authorities=["OWNER_EXPLICIT", "AGENT_SELF"])
    write(repo, f"{AUTH_DIR}/auth-test-agent.json", auth_record("auth-test-agent", ["**"], authority="AGENT_SELF", reusable=True))
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)[0] == 0
    sha = commit(repo, "agent authorizes itself")
    forge_row(repo, sha, ["auth-test-agent"])
    commit_ledger(repo)
    rc, out = run(repo, "verify", "--committed", capsys=capsys)
    assert rc == 1 and f"DISALLOWED_AUTHORITY {sha}: auth-test-agent" in out


def test_editing_an_old_row_fails(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    text = (repo / LEDGER).read_text()
    row = json.loads(text)
    row["authorization_ids"] = ["auth-test-one", "auth-extra"]
    (repo / LEDGER).write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    rc, out = verify(repo, capsys)
    assert rc == 1 and "LEDGER_NOT_APPEND_ONLY worktree" in out
    commit_ledger(repo, "rewrite history in the ledger")
    rc, out = verify(repo, capsys)
    assert rc == 1 and "row(s) of parent" in out


def test_editing_an_authorization_record_in_the_worktree_fails(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    path = repo / f"{AUTH_DIR}/auth-test-one.json"
    path.write_text(path.read_text().replace('"src/a.py"', '"src/**"'))
    rc, out = verify(repo, capsys)
    assert rc == 1 and "AUTHORIZATION_NOT_APPEND_ONLY worktree: M" in out


def test_a_committed_edit_of_an_authorization_record_fails(repo, capsys):
    """I6 case 4: the record post-dates the baseline, so a baseline..HEAD diff shows it as added."""
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    path = repo / f"{AUTH_DIR}/auth-test-one.json"
    path.write_text(path.read_text().replace('"src/a.py"', '"src/**"'))
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)[0] == 3, "record refuses a record edit"
    sha = commit(repo, "widen the record in place")
    forge_row(repo, sha, ["auth-test-one"])
    commit_ledger(repo)
    assert git(repo, "diff", "--name-status", baseline(repo), "HEAD", "--", AUTH_DIR).startswith("A\t")
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"AUTHORIZATION_NOT_APPEND_ONLY {sha}: M {AUTH_DIR}/auth-test-one.json" in out


def test_a_committed_delete_of_an_authorization_record_fails(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    sha = unrecorded_commit(repo, {f"{AUTH_DIR}/auth-test-one.json": None}, "delete the record")
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"AUTHORIZATION_NOT_APPEND_ONLY {sha}: D {AUTH_DIR}/auth-test-one.json" in out


def test_a_non_reusable_record_is_not_picked_up_for_a_new_change(repo, capsys):
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    scoped_authorization(repo, "auth-test-one", ["src/a.py"], [a])
    write(repo, "src/a.py", "a = 2\n")
    git(repo, "add", ".")
    rc, out = run(repo, "record", "--stage", capsys=capsys)
    assert rc == 3
    assert "hint: non-reusable auth-test-one" in out


def test_a_non_reusable_record_does_not_cover_a_commit_outside_its_scope(repo, capsys):
    """I6 case 2: a forged row cites an existing non-reusable record for a new commit."""
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    scoped_authorization(repo, "auth-test-one", ["src/a.py"], [a])
    assert verify(repo, capsys, "--committed")[0] == 0
    evil = unrecorded_commit(repo, {"src/a.py": "a = 'evil'\n"}, "evil")
    forge_row(repo, evil, ["auth-test-one"])
    commit_ledger(repo)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1
    assert f"UNCOVERED_FILES {evil}" in out and f"auth-test-one is not reusable and {evil[:12]} is not in its commit scope" in out
    # record --commit refuses to write that row in the first place.
    rc, out = run(repo, "record", "--commit", evil, "--auth", "auth-test-one", capsys=capsys)
    assert rc == 3 and "REFUSED" in out


def test_a_non_reusable_record_with_no_scope_covers_nothing(repo, capsys):
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    intake(repo, {"auth-test-legacy": auth_record("auth-test-legacy", ["src/a.py"])})
    forge_row(repo, a, ["auth-test-legacy"])
    commit_ledger(repo)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"UNSCOPED_AUTHORIZATION {a}: auth-test-legacy" in out


def test_a_scope_binding_scopes_a_legacy_record(repo, capsys):
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    intake(repo, {"auth-test-legacy": auth_record("auth-test-legacy", ["src/a.py"])})
    forge_row(repo, a, ["auth-test-legacy"])
    commit_ledger(repo)
    intake(repo, {"auth-test-bind": binding_record("auth-test-bind", {"auth-test-legacy": [a]})})
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 0, out
    # A second binding for the same record is refused, not chosen between.
    intake(repo, {"auth-test-bind2": binding_record("auth-test-bind2", {"auth-test-legacy": [a, "f" * 40]})})
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and "bound by more than one scope binding" in out


def test_a_scope_binding_cannot_rescope_a_scoped_record(repo, capsys):
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    scoped_authorization(repo, "auth-test-one", ["src/a.py"], [a])
    evil = unrecorded_commit(repo, {"src/a.py": "a = 'evil'\n"}, "evil")
    forge_row(repo, evil, ["auth-test-one"])
    commit_ledger(repo)
    intake(repo, {"auth-test-widen": binding_record("auth-test-widen", {"auth-test-one": [evil]})})
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1
    assert "INVALID_SCOPE_BINDING auth-test-widen: auth-test-one declares its own scope" in out
    assert f"UNCOVERED_FILES {evil}" in out


def test_a_binding_record_is_not_an_authorization(repo, capsys):
    a = unrecorded_commit(repo, {"src/a.py": "a = 1\n"}, "one")
    intake(repo, {"auth-test-bind": binding_record("auth-test-bind", {"auth-test-x": [a]}, authorized_paths=["**"])})
    forge_row(repo, a, ["auth-test-bind"])
    commit_ledger(repo)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"NOT_AN_AUTHORIZATION {a}: auth-test-bind" in out


def test_a_merge_is_covered_when_it_brings_in_a_scoped_commit(repo, capsys):
    git(repo, "checkout", "-q", "-b", "side")
    s = unrecorded_commit(repo, {"src/side.py": "s = 1\n"}, "side")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    m = git(repo, "rev-parse", "HEAD")
    scoped_authorization(repo, "auth-test-side", ["src/side.py"], [s])
    forge_row(repo, m, ["auth-test-side"])
    commit_ledger(repo)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 0, out
    # A later non-merge commit touching the same file is not in the scope.
    later = unrecorded_commit(repo, {"src/side.py": "s = 2\n"}, "later")
    forge_row(repo, later, ["auth-test-side"])
    commit_ledger(repo)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"UNCOVERED_FILES {later}" in out


def test_the_merge_hook_covers_a_merge_that_brings_in_scoped_commits(repo, capsys):
    """The integrator's pre-merge-commit hook: the merge has no SHA yet, but what it brings in does."""
    git(repo, "checkout", "-q", "-b", "side")
    s = unrecorded_commit(repo, {"src/side.py": "s = 1\n"}, "side")
    scoped_authorization(repo, "auth-test-side", ["src/side.py"], [s])
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    rc, out = run(repo, "record", "--stage", capsys=capsys)
    assert rc == 0, out
    m = commit(repo, "merge side")
    assert json.loads((repo / LEDGER).read_text().splitlines()[-1])["authorization_ids"] == ["auth-test-side"]
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 0, out
    # A plain staged change touching the same file is not covered by that record.
    write(repo, "src/side.py", "s = 2\n")
    git(repo, "add", ".")
    rc, out = run(repo, "record", "--stage", "--auth", "auth-test-side", capsys=capsys)
    assert rc == 3 and "REFUSED" in out
    assert m


def test_a_record_created_in_a_merge_resolution_is_not_carried(repo, capsys):
    git(repo, "checkout", "-q", "-b", "side")
    s = unrecorded_commit(repo, {"src/side.py": "s = 1\n"}, "side")
    scoped_authorization(repo, "auth-test-side", ["src/side.py"], [s])
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    write(repo, f"{AUTH_DIR}/auth-test-sneak.json", auth_record("auth-test-sneak", ["src/**"]))
    git(repo, "add", ".")
    rc, out = run(repo, "record", "--stage", capsys=capsys)
    assert rc == 3 and "auth-test-sneak.json" in out
    run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)
    m = commit(repo, "merge side, and slip a record in")
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"UNCOVERED_FILES {m}: 1 file(s)" in out and "auth-test-sneak.json" in out


def test_glob_star_stays_in_one_directory():
    """I6 case 6: fnmatch let `docs/*` match docs/decisions/x/y.md."""
    cases = [
        ("docs/a.md", "docs/*", True), ("docs/decisions/x/y.md", "docs/*", False),
        ("docs/decisions/x/y.md", "docs/**", True), ("docs/a.md", "docs/**", True),
        ("backend/tests/t.py", "backend/tests/**", True), ("backend/testsX/t.py", "backend/tests/**", False),
        ("a/b/c.py", "**/c.py", True), ("c.py", "**/c.py", True), ("a/b.py", "a/?.py", True),
        ("a/b/c.py", "a/*.py", False), ("x", "**", True),
    ]
    for path, pat, want in cases:
        assert ptl.glob_match(path, pat) is want, (path, pat)


def test_a_single_star_record_does_not_cover_a_subdirectory(repo, capsys):
    write(repo, "docs/decisions/x.md", "decision\n")
    write(repo, "docs/top.md", "top\n")
    git(repo, "add", ".")
    sha = commit(repo, "docs")
    scoped_authorization(repo, "auth-test-docs", ["docs/*"], [sha], expect_covered=False)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"UNCOVERED_FILES {sha}: 1 file(s)" in out and "docs/decisions/x.md" in out


def test_an_append_only_path_may_only_grow(repo, capsys):
    """I6 case 7: '(append-only)' was stripped and ignored, so truncation passed."""
    grow = unrecorded_commit(repo, {"docs/log.yaml": "a: 1\n"}, "create")
    grow2 = unrecorded_commit(repo, {"docs/log.yaml": "a: 1\nb: 2\n"}, "append")
    cut = unrecorded_commit(repo, {"docs/log.yaml": "truncated: true\n"}, "truncate")
    gone = unrecorded_commit(repo, {"docs/log.yaml": None}, "delete")
    scoped_authorization(repo, "auth-test-log", ["docs/log.yaml (append-only)"], [grow, grow2, cut, gone], expect_covered=False)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1
    assert f"UNCOVERED_FILES {cut}" in out and "does not keep the old content as a prefix" in out
    assert f"UNCOVERED_FILES {gone}" in out
    assert f"UNCOVERED_FILES {grow}" not in out and f"UNCOVERED_FILES {grow2}" not in out


def test_an_unrecognised_annotation_covers_nothing(repo, capsys):
    sha = unrecorded_commit(repo, {"docs/p.md": "x\n"}, "one")
    scoped_authorization(repo, "auth-test-p", ["docs/p.md (provenance correction only)"], [sha], expect_covered=False)
    rc, out = verify(repo, capsys, "--committed")
    assert rc == 1 and f"UNCOVERED_FILES {sha}" in out and "cannot enforce" in out


# ------------------------------------------------------------------ merges and supersession

def test_a_merge_commit_is_diffed_against_its_first_parent(repo, capsys):
    reusable_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    git(repo, "checkout", "-q", "-b", "side")
    reusable_commit(repo, "auth-test-side", {"src/side.py": "s = 1\n"}, "side")
    git(repo, "checkout", "-q", "main")
    reusable_commit(repo, "auth-test-main", {"src/main.py": "m = 1\n"}, "main")
    proc = subprocess.run(["git", "merge", "--no-ff", "--no-commit", "side"], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:  # both sides appended to the ledger: keep both, in order
        ours = git(repo, "show", f"HEAD:{LEDGER}").splitlines()
        theirs = git(repo, "show", f"side:{LEDGER}").splitlines()
        (repo / LEDGER).write_text("\n".join(ours + [x for x in theirs if x not in ours]) + "\n")
        git(repo, "add", LEDGER)
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    sha = commit(repo, "merge side")
    parents = git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
    row = json.loads((repo / LEDGER).read_text().splitlines()[-1])
    assert row["merge"] is True and row["parents"] == parents
    assert row["authorization_ids"] == ["auth-test-side"], "a merge inherits the ids recorded for what it brings in"
    assert row["changed_files"] == [f"{AUTH_DIR}/auth-test-side.json", "src/side.py"]
    assert row["commit_diff_sha256"] == ptl.commit_digest(ptl.Repo(repo), sha)
    rc, out = verify(repo, capsys)
    assert rc == 0, out


def test_supersession_adds_coverage(repo, capsys):
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)[0] == 0
    old = commit(repo, "made before anyone recorded authority")
    rc, out = verify(repo, capsys)
    assert rc == 1 and f"UNCOVERED_FILES {old}" in out
    # The owner's later authority arrives as a new record naming the commit ...
    intake(repo, {"auth-test-later": auth_record("auth-test-later", ["src/a.py"], commit_scope={"commits": [old]})})
    # ... and a supersession row for the old commit adds the id without editing its row.
    before = (repo / LEDGER).read_text()
    rc, out = run(repo, "record", "--commit", old, "--auth", "auth-test-later", capsys=capsys)
    assert rc == 0, out
    after = (repo / LEDGER).read_text()
    assert after.startswith(before)
    new = json.loads(after.splitlines()[-1])
    assert new["kind"] == "supersession" and new["commit_sha"] == old
    assert new["authorization_ids"] == ["auth-test-later"]
    rc, out = verify(repo, capsys)
    assert rc == 0, out
    # A second supersession for an already-covered commit writes nothing.
    assert run(repo, "record", "--commit", old, "--auth", "auth-test-later", capsys=capsys)[0] == 0
    assert (repo / LEDGER).read_text() == after


def test_record_range_fills_rows_for_commits_made_without_the_hook(repo, capsys):
    shas = [unrecorded_commit(repo, {f"src/u{n}.py": f"u = {n}\n"}, f"unit {n}") for n in range(3)]
    rc, out = verify(repo, capsys)
    assert rc == 1 and all(f"MISSING_ROW {s}" in out for s in shas)
    intake(repo, {"auth-test-units": auth_record("auth-test-units", ["src/**"], commit_scope={"commits": shas})})
    rc, out = run(repo, "record", "--range", f"{baseline(repo)}..HEAD", "--auth", "auth-test-units", capsys=capsys)
    assert rc == 0, out
    rc, out = verify(repo, capsys)
    assert rc == 0, out


# ------------------------------------------------------------------ verify-pr: the base decides

def _base_with_config(repo: Path, capsys) -> str:
    """main carries the config (baseline = root) and a reusable record, like a programme branch."""
    set_config(repo, [{"id": "t", "baseline_sha": baseline(repo)}])
    write(repo, f"{AUTH_DIR}/auth-test-tools.json",
          auth_record("auth-test-tools", [CONFIG, "src/**", f"{AUTH_DIR}/auth-test-tools.json"], reusable=True))
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    return commit(repo, "config and tooling authority")


def test_verify_pr_checks_from_the_merge_base(repo, capsys):
    base = _base_with_config(repo, capsys)
    git(repo, "checkout", "-q", "-b", "pr")
    write(repo, "src/pr.py", "p = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    commit(repo, "pr")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 0, out
    sha = unrecorded_commit(repo, {"src/pr.py": "p = 2\n"}, "unrecorded")
    rc, out = run(repo, "verify-pr", "--base", "main", capsys=capsys)
    assert rc == 1 and f"MISSING_ROW {sha}" in out and "MISSING_ROW " + base not in out


def test_verify_pr_skips_history_before_the_baseline(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    pre = unrecorded_commit(repo, {"src/pre.py": "unrecorded before the baseline\n"}, "before enforcement")
    set_config(repo, [{"id": "t", "baseline_sha": pre}])
    write(repo, f"{AUTH_DIR}/auth-test-cfg.json", auth_record("auth-test-cfg", [CONFIG, "src/**", f"{AUTH_DIR}/auth-test-cfg.json"], reusable=True))
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    trusted = commit(repo, "config")
    git(repo, "checkout", "-q", "-b", "pr")
    write(repo, "src/pr.py", "p = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    commit(repo, "pr")
    rc, out = run(repo, "verify-pr", "--base", trusted, capsys=capsys)
    assert rc == 0, out
    assert "MISSING_ROW " + pre not in out and base


def test_verify_pr_refuses_a_base_without_config(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "pr")
    set_config(repo, [{"id": "t", "baseline_sha": base}])
    git(repo, "add", ".")
    commit(repo, "the PR brings its own config")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 2 and "refusing to guess" in out


def test_a_record_added_by_the_pr_cannot_authorize_it(repo, capsys):
    """I6 case 3: a PR adds an OWNER_EXPLICIT '**' record and cites it for its own code."""
    base = _base_with_config(repo, capsys)
    git(repo, "checkout", "-q", "-b", "pr")
    write(repo, f"{AUTH_DIR}/auth-test-self.json", auth_record("auth-test-self", ["**"], authority="OWNER_EXPLICIT", reusable=True))
    write(repo, "evil.py", "evil = True\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    sha = commit(repo, "self-authorized")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 1
    assert f"UNTRUSTED_AUTHORIZATION {sha}: auth-test-self: added by this change" in out
    assert f"UNCOVERED_FILES {sha}" in out


def test_a_record_split_into_its_own_pr_commit_still_cannot_authorize_the_pr(repo, capsys):
    base = _base_with_config(repo, capsys)
    git(repo, "checkout", "-q", "-b", "pr")
    intake(repo, {"auth-test-self": auth_record("auth-test-self", ["**"], authority="OWNER_EXPLICIT", reusable=True)})
    write(repo, "evil.py", "evil = True\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    sha = commit(repo, "uses the record from the previous commit")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 1 and f"UNTRUSTED_AUTHORIZATION {sha}: auth-test-self" in out


def test_bootstrap_merges_the_record_first(repo, capsys):
    """The documented integrator path: intake PR first (records only), then the code, verified against it."""
    base = _base_with_config(repo, capsys)
    git(repo, "checkout", "-q", "-b", "unit")
    c1 = unrecorded_commit(repo, {"tools/checker.py": "v = 2\n"}, "unit code")
    record = auth_record("auth-test-unit", ["tools/checker.py"], commit_scope={"commits": [c1]})
    intake(repo, {"auth-test-unit": record}, "unit intake")
    assert run(repo, "record", "--commit", c1, "--auth", "auth-test-unit", capsys=capsys)[0] == 0
    commit_ledger(repo)
    # One PR carrying record and code is refused: the record is not on the base yet.
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 1 and f"UNTRUSTED_AUTHORIZATION {c1}: auth-test-unit" in out
    # Step 1: the intake alone, as its own PR onto the base. It passes: nothing is authorized by it yet.
    git(repo, "checkout", "-q", "-b", "intake", base)
    intake(repo, {"auth-test-unit": record}, "intake PR")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 0, out
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--ff-only", "intake")
    # Step 2: the unit's commits against the base that now holds the record.
    rc, out = run(repo, "verify-pr", "--base", "main", "--head", "unit", capsys=capsys)
    assert rc == 0, out


def test_a_pr_cannot_move_its_own_baseline(repo, capsys):
    """I6 case 8: a new lineage whose baseline is the PR's own unrowed commit."""
    base = _base_with_config(repo, capsys)
    git(repo, "checkout", "-q", "-b", "pr")
    evil = unrecorded_commit(repo, {"src/evil.py": "evil = True\n"}, "evil, no row")
    set_config(repo, [{"id": "t", "baseline_sha": baseline(repo)}, {"id": "evil", "baseline_sha": evil}])
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    commit(repo, "baseline past the evil commit")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 1 and f"MISSING_ROW {evil}" in out


def test_a_baseline_must_be_an_ancestor_of_the_base(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "side")
    side = unrecorded_commit(repo, {"src/s.py": "s\n"}, "side")
    git(repo, "checkout", "-q", "main")
    config = {"lineages": [{"id": "root", "baseline_sha": base}, {"id": "side", "baseline_sha": side}]}
    r = ptl.Repo(repo)
    assert ptl.nearest_baseline(r, config, side)[0] == side
    assert ptl.nearest_baseline(r, config, side, anchor=base)[0] == base


def test_a_pr_that_revokes_a_record_history_relies_on_is_refused(repo, capsys):
    """I6 case 5: revocation through a later record fails the history that relied on it."""
    base = _base_with_config(repo, capsys)
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    used = commit(repo, "history relying on auth-test-tools")
    git(repo, "checkout", "-q", "-b", "pr")
    intake(repo, {"auth-test-revoker": auth_record("auth-test-revoker", ["nothing"], revokes=["auth-test-tools"])})
    rc, out = run(repo, "verify-pr", "--base", "main", capsys=capsys)
    assert rc == 1
    assert f"HISTORY_BROKEN_BY_CHANGE REVOKED_AUTHORIZATION {used}: auth-test-tools: revoked by auth-test-revoker" in out
    assert base


def test_a_pr_config_cannot_widen_allowed_authorities(repo, capsys):
    """I6 case 9 through verify-pr: the base's config is used, and it can only narrow anyway."""
    base = _base_with_config(repo, capsys)
    git(repo, "checkout", "-q", "-b", "pr")
    set_config(repo, [{"id": "t", "baseline_sha": baseline(repo)}], allowed_authorities=["OWNER_DERIVED", "AGENT_SELF"])
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    commit(repo, "config widening, itself authorized by the base's tooling record")
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 0, out  # the change itself is authorized; it just has no effect on this run
    assert json.loads(ptl.Repo(repo).show(base, CONFIG)).get("allowed_authorities") is None


# ------------------------------------------------------------------ the real hook, end to end

def test_the_installed_hook_records_the_commit(repo, capsys):
    shutil.copytree(ROOT / ".githooks", repo / ".githooks")
    write(repo, "tools/ci/project_truth_ledger.py", CHECKER.read_text())
    shutil.copy(ROOT / "tools" / "ci" / "install_project_truth_hooks.sh", repo / "tools" / "ci" / "install_project_truth_hooks.sh")
    git(repo, "config", "--unset", "core.hooksPath")
    subprocess.run(["sh", "tools/ci/install_project_truth_hooks.sh"], cwd=repo, check=True, stdout=subprocess.PIPE)
    assert git(repo, "config", "core.hooksPath") == ".githooks"
    paths = [".githooks/pre-commit", ".githooks/pre-merge-commit", "tools/ci/project_truth_ledger.py",
             "tools/ci/install_project_truth_hooks.sh", f"{AUTH_DIR}/auth-test-tooling.json"]
    write(repo, f"{AUTH_DIR}/auth-test-tooling.json", auth_record("auth-test-tooling", paths, reusable=True))
    git(repo, "add", ".")
    env = {**os.environ, "PYTHON": sys.executable}
    env.pop("PROJECT_TRUTH_ALLOW_UNCOVERED", None)
    subprocess.run(["git", "commit", "-q", "-m", "tooling"], cwd=repo, check=True, env=env)
    assert git(repo, "show", "--name-only", "--format=", "HEAD").count(LEDGER) == 1, "the hook stages its row into the commit"
    # The hook refuses a commit nothing authorizes, and the commit does not happen.
    write(repo, "src/x.py", "x = 1\n")
    git(repo, "add", ".")
    head = git(repo, "rev-parse", "HEAD")
    proc = subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode != 0 and "REFUSED" in proc.stderr
    assert git(repo, "rev-parse", "HEAD") == head
    # With PROJECT_TRUTH_ALLOW_UNCOVERED=1 the gap is recorded truthfully, and verify fails on it.
    proc = subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, env={**env, "PROJECT_TRUTH_ALLOW_UNCOVERED": "1"},
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, proc.stderr
    row = json.loads((repo / LEDGER).read_text().splitlines()[-1])
    assert row["uncovered_files"] == ["src/x.py"]
    rc, out = verify(repo, capsys)
    assert rc == 1 and "UNCOVERED_FILES" in out


# ------------------------------------------------------------------ the real branch and CI

def _history_available() -> bool:
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    if shallow.stdout.strip() != "false":
        return False
    config = json.loads((ROOT / CONFIG).read_text())
    return any(subprocess.run(["git", "merge-base", "--is-ancestor", x["baseline_sha"], "HEAD"], cwd=ROOT).returncode == 0
               for x in config["lineages"])


@pytest.mark.skipif(not _history_available(), reason="shallow checkout: the project-truth-ledger CI job runs this with full history")
def test_the_real_branch_verifies_at_head(capsys):
    rc = ptl.main(["--repo", str(ROOT), "verify", "--committed"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "GREEN" in out


def test_ci_runs_the_base_refs_checker_against_the_head():
    """I6 case 10: the job ran the PR's own checker, so a PR could replace it."""
    for wf in (ROOT / ".github" / "workflows" / "van-ci.yml", ROOT / "tools" / "ci" / "github-actions-ci.yml"):
        text = wf.read_text(encoding="utf-8")
        job = text.split("  project-truth-ledger:", 1)[1].split("\n  backend:", 1)[0]
        assert "path: trusted" in job and "path: head" in job and "fetch-depth: 0" in job
        assert "python trusted/tools/ci/project_truth_ledger.py --repo head verify-pr" in job
        assert "run: python tools/ci/project_truth_ledger.py" not in job, "the gate must not run the PR's own checker"
        assert "github.event.pull_request.base.sha" in job
        on_push = text.split("  push:", 1)[1].split("  pull_request:", 1)[0]
        assert "'gpt/**'" in on_push, "programme branches are verified on push too"


def test_a_push_is_judged_from_a_protected_ref_not_the_pushed_history():
    """Review I7 minor 9: the push path took its trusted checker from github.event.before — the
    branch's previous head, which on an unprotected branch whoever pushes controls (push a
    checker edit, then push again). The trusted side of a push is now a protected ref."""
    for wf in (ROOT / ".github" / "workflows" / "van-ci.yml", ROOT / "tools" / "ci" / "github-actions-ci.yml"):
        text = wf.read_text(encoding="utf-8")
        job = text.split("  project-truth-ledger:", 1)[1].split("\n  backend:", 1)[0]
        env = job.split("    env:", 1)[1].split("    steps:", 1)[0]
        assert "TRUSTED_SHA" not in env, "the trusted SHA is computed, never taken from the event"
        step = job.split("name: Trusted ref", 1)[1].split("- uses: actions/checkout@v4", 1)[0]
        assert "refs/protected/" in step and "git merge-base HEAD" in step
        assert "git merge-base --is-ancestor \"$trusted\" HEAD" in step  # a protected branch: fast-forward only
        assert '"$DEFAULT_BRANCH"|gpt/*)' in step  # only protected branches may use their previous head
        assert 'echo "TRUSTED_SHA=$trusted" >> "$GITHUB_ENV"' in step
        order = [job.index("path: head"), job.index("name: Trusted ref"), job.index("path: trusted")]
        assert order == sorted(order), "the trusted ref is computed before the trusted side is checked out"


def test_codeowners_guard_the_governance_paths():
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    rules = {line.split()[0]: line.split()[1:] for line in owners.splitlines() if line.strip() and not line.startswith("#")}
    for pattern in ("/docs/project-state/authorizations/", "/registries/project_truth_ledger_baselines.json",
                    "/tools/ci/", "/.githooks/", "/.github/workflows/", "/.github/CODEOWNERS"):
        assert rules.get(pattern), f"CODEOWNERS has no owner for {pattern}"


def test_the_baselines_are_declared_with_the_gap_recorded():
    config = json.loads((ROOT / CONFIG).read_text())
    ids = {x["id"]: x["baseline_sha"] for x in config["lineages"]}
    assert ids == {
        "programme-b-jev-openmuse-convergence-r1": "a16f7cb80b0169f93471d71bf6adab6cf03f7bf5",
        "programme-a-memory-fabric-rev1-2": "12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af",
    }
    assert config["unenforced_history"]["status"] == "KNOWN_GAP_NOT_ENFORCED"
