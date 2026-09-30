"""Owner decision 2026-09-30: "enforce van's ledger".

`tools/ci/project_truth_ledger.py` is the only thing that reads LOCAL_CHANGE_LEDGER.jsonl, so
each failure it exists to catch is induced here in a throwaway repository and watched to
fail: a commit with no row, a row whose digest was altered, a file no authorization covers,
an authorization that does not exist or was revoked, an edited row or record. The passing
paths (hook row binding to its commit, merges, supersession) are checked the same way, and
the real branch is verified at HEAD.
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
CHECKER = ROOT / "tools" / "ci" / "project_truth_ledger.py"
LEDGER = "docs/project-state/LOCAL_CHANGE_LEDGER.jsonl"
AUTH_DIR = "docs/project-state/authorizations"

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


def authorized_commit(root: Path, aid: str, files: dict[str, str], msg: str) -> str:
    """A commit made the way the pre-commit hook makes it: record the staged change, commit."""
    write(root, f"{AUTH_DIR}/{aid}.json", auth_record(aid, [*files, f"{AUTH_DIR}/{aid}.json"]))
    for rel, text in files.items():
        write(root, rel, text)
    git(root, "add", ".")
    assert ptl.main(["--repo", str(root), "record", "--stage"]) == 0
    return commit(root, msg)


def verify(root: Path, capsys) -> tuple[int, str]:
    return run(root, "verify", "--baseline", baseline(root), capsys=capsys)


# ------------------------------------------------------------------ passing paths

def test_a_hook_row_binds_to_the_commit_it_becomes(repo, capsys):
    sha = authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n", "img.bin": "\x00\x01"}, "one")
    rows = [json.loads(x) for x in (repo / LEDGER).read_text().splitlines()]
    assert len(rows) == 1 and "commit_sha" not in rows[0]
    assert rows[0]["parent_sha"] == baseline(repo)
    assert rows[0]["commit_diff_sha256"] == ptl.commit_digest(ptl.Repo(repo), sha)
    assert rows[0]["authorization_ids"] == ["auth-test-one"]
    rc, out = verify(repo, capsys)
    assert rc == 0, out
    assert "GREEN" in out


def test_a_ledger_only_commit_needs_no_row(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    with (repo / LEDGER).open("a") as fh:
        fh.write(json.dumps({"kind": "note"}) + "\n")
    git(repo, "add", LEDGER)
    commit(repo, "ledger only")
    rc, out = verify(repo, capsys)
    assert rc == 0, out


# ------------------------------------------------------------------ induced failures

def test_a_commit_with_no_row_fails(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    write(repo, "src/a.py", "a = 2\n")
    git(repo, "add", ".")
    sha = commit(repo, "no hook")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"MISSING_ROW {sha}" in out


def test_a_tampered_digest_fails(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    write(repo, "src/a.py", "a = 2\n")
    git(repo, "add", ".")
    sha = commit(repo, "recorded afterwards")
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
    sha = authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    text = (repo / LEDGER).read_text()
    (repo / LEDGER).write_text(text.replace(json.loads(text)["commit_diff_sha256"], "f" * 64))
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"MISSING_ROW {sha}" in out


def test_an_uncovered_file_fails_and_record_refuses_it(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-one.json", auth_record("auth-test-one", ["src/a.py", f"{AUTH_DIR}/auth-test-one.json"]))
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
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    sha = commit(repo, "one")
    row = {"schema_version": 2, "commit_sha": sha, "parent_sha": baseline(repo), "changed_files": ["src/a.py"],
           "commit_diff_sha256": ptl.commit_digest(ptl.Repo(repo), sha), "authorization_ids": ["auth-does-not-exist"]}
    with (repo / LEDGER).open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"UNKNOWN_AUTHORIZATION {sha}" in out
    assert f"UNCOVERED_FILES {sha}" in out


def test_a_revoked_authorization_fails(repo, capsys):
    sha = authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    assert verify(repo, capsys)[0] == 0
    # Revocation is itself append-only: a later record names the one it withdraws.
    write(repo, f"{AUTH_DIR}/auth-test-revoke2.json",
          auth_record("auth-test-revoke2", [f"{AUTH_DIR}/auth-test-revoke2.json"], revokes=["auth-test-one"]))
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    commit(repo, "revoke one")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"REVOKED_AUTHORIZATION {sha}: auth-test-one: revoked by auth-test-revoke2" in out


def test_a_record_marked_revoked_fails(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-dead.json", auth_record("auth-test-dead", ["src/a.py", f"{AUTH_DIR}/auth-test-dead.json"], revoked=True))
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    rc, out = run(repo, "record", "--stage", "--auth", "auth-test-dead", capsys=capsys)
    assert rc == 2 and "REVOKED_AUTHORIZATION" in out
    sha = commit(repo, "one")
    row = {"schema_version": 2, "commit_sha": sha, "parent_sha": baseline(repo),
           "commit_diff_sha256": ptl.commit_digest(ptl.Repo(repo), sha), "authorization_ids": ["auth-test-dead"]}
    with (repo / LEDGER).open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    rc, out = verify(repo, capsys)
    assert rc == 1
    assert f"REVOKED_AUTHORIZATION {sha}: auth-test-dead: record says revoked" in out


def test_a_no_authority_record_fails(repo, capsys):
    write(repo, f"{AUTH_DIR}/auth-test-none.json", auth_record("auth-test-none", ["src/a.py", f"{AUTH_DIR}/auth-test-none.json"], authority="NO_AUTHORITY"))
    write(repo, "src/a.py", "a = 1\n")
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", "--allow-uncovered", capsys=capsys)[0] == 0
    sha = commit(repo, "one")
    rc, out = verify(repo, capsys)
    assert rc == 1 and f"UNCOVERED_FILES {sha}" in out


def test_editing_an_old_row_fails(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    text = (repo / LEDGER).read_text()
    row = json.loads(text)
    row["authorization_ids"] = ["auth-test-one", "auth-extra"]
    (repo / LEDGER).write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    rc, out = verify(repo, capsys)
    assert rc == 1 and "LEDGER_NOT_APPEND_ONLY worktree" in out
    git(repo, "add", LEDGER)
    commit(repo, "rewrite history in the ledger")
    rc, out = verify(repo, capsys)
    assert rc == 1 and "row(s) of parent" in out


def test_editing_an_authorization_record_fails(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    path = repo / f"{AUTH_DIR}/auth-test-one.json"
    path.write_text(path.read_text().replace('"src/a.py"', '"src/**"'))
    rc, out = verify(repo, capsys)
    assert rc == 1 and "AUTHORIZATION_NOT_APPEND_ONLY worktree: M" in out


def test_a_non_reusable_record_is_not_picked_up_for_a_new_change(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    write(repo, "src/a.py", "a = 2\n")
    git(repo, "add", ".")
    rc, out = run(repo, "record", "--stage", capsys=capsys)
    assert rc == 3
    assert "hint: non-reusable auth-test-one" in out


# ------------------------------------------------------------------ merges and supersession

def test_a_merge_commit_is_diffed_against_its_first_parent(repo, capsys):
    authorized_commit(repo, "auth-test-one", {"src/a.py": "a = 1\n"}, "one")
    git(repo, "checkout", "-q", "-b", "side")
    authorized_commit(repo, "auth-test-side", {"src/side.py": "s = 1\n"}, "side")
    git(repo, "checkout", "-q", "main")
    authorized_commit(repo, "auth-test-main", {"src/main.py": "m = 1\n"}, "main")
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
    # The owner's later authority arrives as a new record, committed with its own row ...
    write(repo, f"{AUTH_DIR}/auth-test-later.json", auth_record("auth-test-later", ["src/a.py", f"{AUTH_DIR}/auth-test-later.json"]))
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    commit(repo, "later authority")
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
    write(repo, f"{AUTH_DIR}/auth-test-units.json", auth_record("auth-test-units", ["src/**", f"{AUTH_DIR}/auth-test-units.json"]))
    git(repo, "add", ".")
    assert run(repo, "record", "--stage", capsys=capsys)[0] == 0
    start = commit(repo, "authority for the units")
    shas = []
    for n in range(3):
        write(repo, f"src/u{n}.py", f"u = {n}\n")
        git(repo, "add", ".")
        shas.append(commit(repo, f"unit {n}"))
    rc, out = verify(repo, capsys)
    assert rc == 1 and all(f"MISSING_ROW {s}" in out for s in shas)
    rc, out = run(repo, "record", "--range", f"{start}..HEAD", "--auth", "auth-test-units", capsys=capsys)
    assert rc == 0, out
    rc, out = verify(repo, capsys)
    assert rc == 0, out


def test_verify_pr_checks_from_the_merge_base(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    write(repo, "src/pre.py", "unrecorded before the baseline\n")
    git(repo, "add", ".")
    pre = commit(repo, "before enforcement")
    git(repo, "checkout", "-q", "-b", "pr")
    authorized_commit(repo, "auth-test-pr", {"src/pr.py": "p = 1\n"}, "pr")
    # The enforcement baseline is `pre`; verify-pr must not demand a row for it.
    write(repo, "registries/project_truth_ledger_baselines.json",
          json.dumps({"lineages": [{"id": "t", "baseline_sha": pre}]}))
    rc, out = run(repo, "verify-pr", "--base", base, capsys=capsys)
    assert rc == 0, out
    assert "unenforced_before_baseline: 1 commit(s)" in out
    write(repo, "src/pr.py", "p = 2\n")
    git(repo, "add", "src/pr.py")
    sha = commit(repo, "unrecorded")
    rc, out = run(repo, "verify-pr", "--base", "main", capsys=capsys)
    assert rc == 1 and f"MISSING_ROW {sha}" in out and "MISSING_ROW " + pre not in out


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
    write(repo, f"{AUTH_DIR}/auth-test-tooling.json", auth_record("auth-test-tooling", paths))
    git(repo, "add", ".")
    env = {**os.environ, "PYTHON": sys.executable}
    subprocess.run(["git", "commit", "-q", "-m", "tooling"], cwd=repo, check=True, env=env)
    assert git(repo, "show", "--name-only", "--format=", "HEAD").count(LEDGER) == 1, "the hook stages its row into the commit"
    # The hook refuses a commit nothing authorizes, and the commit does not happen.
    write(repo, "src/x.py", "x = 1\n")
    git(repo, "add", ".")
    head = git(repo, "rev-parse", "HEAD")
    proc = subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode != 0 and "REFUSED" in proc.stderr
    assert git(repo, "rev-parse", "HEAD") == head
    git(repo, "reset", "-q", "--hard")
    rc, out = verify(repo, capsys)
    assert rc == 0, out


# ------------------------------------------------------------------ the real branch and CI

def _history_available() -> bool:
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    if shallow.stdout.strip() != "false":
        return False
    config = json.loads((ROOT / "registries" / "project_truth_ledger_baselines.json").read_text())
    return any(subprocess.run(["git", "merge-base", "--is-ancestor", x["baseline_sha"], "HEAD"], cwd=ROOT).returncode == 0
               for x in config["lineages"])


@pytest.mark.skipif(not _history_available(), reason="shallow checkout: the project-truth-ledger CI job runs this with full history")
def test_the_real_branch_verifies_at_head(capsys):
    rc = ptl.main(["--repo", str(ROOT), "verify", "--committed"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "GREEN" in out


def test_ci_runs_the_ledger_check_on_pull_requests():
    workflow = (ROOT / ".github" / "workflows" / "van-ci.yml").read_text(encoding="utf-8")
    assert "python tools/ci/project_truth_ledger.py verify-pr --base ${{ github.event.pull_request.base.sha }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow


def test_the_baselines_are_declared_with_the_gap_recorded():
    config = json.loads((ROOT / "registries" / "project_truth_ledger_baselines.json").read_text())
    ids = {x["id"]: x["baseline_sha"] for x in config["lineages"]}
    assert ids == {
        "programme-b-jev-openmuse-convergence-r1": "a16f7cb80b0169f93471d71bf6adab6cf03f7bf5",
        "programme-a-memory-fabric-rev1-2": "12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af",
    }
    assert config["unenforced_history"]["status"] == "KNOWN_GAP_NOT_ENFORCED"
