#!/usr/bin/env python3
"""VAN Project Truth ledger: record rows and verify that history carries them.

`docs/project-state/LOCAL_CHANGE_LEDGER.jsonl` said which change was made under which owner
authority, but nothing read it: a commit with no row, a row whose digest described some other
change, or a row naming an authorization that does not exist all passed every gate. This tool
is the reader. It is modelled on DDS `scripts/project_truth_local.py` but keeps VAN's own
per-commit ledger shape and authorization records.

Modes
-----
record
    Append a row. With no --commit/--range it records the *staged* change: that is what the
    pre-commit and pre-merge-commit hooks in `.githooks/` call; hooks take no arguments, so
    PROJECT_TRUTH_AUTH=<id>[,<id>] names authorizations there. The row is keyed by
    (parent_sha, commit_diff_sha256) because the commit SHA does not exist yet. With
    --commit SHA (repeatable) or --range A..B it records commits that already exist, keyed by
    commit_sha; the integrator uses this for commits made without the hook (rebase,
    cherry-pick, another worktree with no hook installed, amend).
verify [--baseline SHA]
    Every commit in baseline..HEAD must have a bound row whose digest matches the commit, and
    every changed file must be covered by a valid authorization the rows name. Without
    --baseline the nearest enforcement baseline in
    `registries/project_truth_ledger_baselines.json` that is an ancestor of HEAD is used.
verify-pr --base SHA
    The same check over merge-base(SHA, HEAD)..HEAD, starting no earlier than the enforcement
    baseline of this lineage. For CI on pull requests.

Diff digest (the recipe unit G6c used for the retroactive Programme B rows)
    sha256(git diff --binary --no-ext-diff --no-renames <parent> <commit>
           -- . ':(exclude)docs/project-state/LOCAL_CHANGE_LEDGER.jsonl')
    Merge commits are diffed against their first parent. The staged form
    (`git diff --cached ...` against HEAD) produces the same bytes as the committed form, so a
    row written by the pre-commit hook binds to the commit it becomes.

Row binding and supersession
    A row binds to commit C when either
      * row.commit_sha == C, or
      * the row has no commit_sha, row.parent_sha == first parent of C, and
        row.commit_diff_sha256 == digest(C)   (rows written by the pre-commit hook).
    Every bound row carrying commit_sha == C must also carry the correct digest; a row that
    names C with a different digest is a tamper finding even if another row is correct.
    Rows are never edited. A later row for the same commit (kind "supersession") adds
    authorization ids. The effective authorization of C is the UNION of authorization_ids
    over all rows bound to C. Supersession can only add coverage; it cannot remove it.
    Withdrawing authority is done by revoking the authorization record (a record with
    "revoked": true, or a later record listing the id under "revokes"), which fails every
    commit that relies on it.

Coverage
    A changed file (the ledger itself excepted) is covered when one of the effective
    authorization ids names a record in `docs/project-state/authorizations/<id>.json` that
    exists in the verified tree, is not revoked, has an authority in the configured allowed
    set, lists the path (exactly or by glob; trailing " (...)" annotations are ignored) in
    authorized_paths and does not list it in excluded_paths. Authorization records are
    looked up at the verified head, not at the commit, so retroactive records are honoured;
    records must be append-only (added, never modified or deleted) across the range.

Commits whose diff touches only the ledger are exempt from needing a row (they cannot name
their own SHA). The ledger must be append-only across the range: every row present in a
parent must still be present in the child.

Exit codes: 0 green, 1 verification failed, 2 usage/config error, 3 record refused (files not
covered by any selectable authorization; nothing written).
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LEDGER_REL = "docs/project-state/LOCAL_CHANGE_LEDGER.jsonl"
AUTH_DIR_REL = "docs/project-state/authorizations"
CONFIG_REL = "registries/project_truth_ledger_baselines.json"
DEFAULT_ALLOWED = ("OWNER_EXPLICIT", "OWNER_DERIVED", "OWNER_DELEGATED_AUTONOMY")
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DIFF_RECIPE = (
    "sha256(git diff --binary --no-ext-diff --no-renames <parent_sha> <commit_sha> -- . "
    "':(exclude)docs/project-state/LOCAL_CHANGE_LEDGER.jsonl'); first parent for merges"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# Pin the diff-header options a user's config could change, so the digest depends on the
# change and not on whoever computed it. These are git's defaults.
GIT_PIN = [
    "-c", "diff.noprefix=false",
    "-c", "diff.mnemonicPrefix=false",
    "-c", "diff.relative=false",
    "-c", "core.quotePath=true",
    "-c", "color.ui=never",
]


class Repo:
    def __init__(self, root: Path):
        self.root = root

    def git(self, *args: str, check: bool = True, binary: bool = False) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", *GIT_PIN, *args],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
        )
        if check and proc.returncode != 0:
            err = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode(errors="replace")
            raise RuntimeError(f"git {' '.join(args)} failed: {err.strip()}")
        return proc

    def out(self, *args: str) -> str:
        return self.git(*args).stdout.strip()

    def ok(self, *args: str) -> bool:
        return self.git(*args, check=False).returncode == 0

    def resolve(self, ref: str) -> str | None:
        proc = self.git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def parents(self, sha: str) -> list[str]:
        return self.out("rev-list", "--parents", "-n", "1", sha).split()[1:]

    def is_ancestor(self, a: str, b: str) -> bool:
        return self.ok("merge-base", "--is-ancestor", a, b)

    def show(self, ref: str, path: str) -> str | None:
        proc = self.git("show", f"{ref}:{path}", check=False)
        return proc.stdout if proc.returncode == 0 else None


# --------------------------------------------------------------------------- diff digests

def _pathspec() -> list[str]:
    return ["--", ".", f":(exclude){LEDGER_REL}"]


def commit_files(repo: Repo, sha: str) -> list[str]:
    ps = repo.parents(sha)
    parent = ps[0] if ps else EMPTY_TREE
    out = repo.out("diff", "--name-only", "--no-renames", parent, sha, *_pathspec())
    return [x for x in out.splitlines() if x]


def commit_digest(repo: Repo, sha: str) -> str:
    ps = repo.parents(sha)
    parent = ps[0] if ps else EMPTY_TREE
    raw = repo.git("diff", "--binary", "--no-ext-diff", "--no-renames", parent, sha, *_pathspec(), binary=True).stdout
    return hashlib.sha256(raw).hexdigest()


def commit_name_status(repo: Repo, sha: str) -> list[tuple[str, str]]:
    ps = repo.parents(sha)
    parent = ps[0] if ps else EMPTY_TREE
    out = repo.out("diff", "--name-status", "--no-renames", parent, sha, *_pathspec())
    return [tuple(x.split("\t", 1)) for x in out.splitlines() if "\t" in x]  # type: ignore[misc]


def staged_files(repo: Repo) -> list[str]:
    out = repo.out("diff", "--cached", "--name-only", "--no-renames", *_pathspec())
    return [x for x in out.splitlines() if x]


def staged_digest(repo: Repo) -> str:
    raw = repo.git("diff", "--cached", "--binary", "--no-ext-diff", "--no-renames", *_pathspec(), binary=True).stdout
    return hashlib.sha256(raw).hexdigest()


def staged_name_status(repo: Repo) -> list[tuple[str, str]]:
    out = repo.out("diff", "--cached", "--name-status", "--no-renames", *_pathspec())
    return [tuple(x.split("\t", 1)) for x in out.splitlines() if "\t" in x]  # type: ignore[misc]


# --------------------------------------------------------------------------- ledger

def parse_rows(text: str | None) -> tuple[list[dict], list[str]]:
    rows, bad = [], []
    for n, line in enumerate((text or "").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            bad.append(f"line {n}: not JSON")
            continue
        if not isinstance(row, dict):
            bad.append(f"line {n}: not an object")
            continue
        rows.append(row)
    return rows, bad


def ledger_lines(text: str | None) -> collections.Counter:
    return collections.Counter(x for x in (text or "").splitlines() if x.strip())


def serialize(row: dict) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def bound_rows(rows: list[dict], sha: str, parent: str | None, digest: str) -> list[dict]:
    out = []
    for r in rows:
        if r.get("commit_sha") == sha:
            out.append(r)
        elif not r.get("commit_sha") and r.get("parent_sha") == parent and r.get("commit_diff_sha256") == digest:
            out.append(r)
    return out


# --------------------------------------------------------------------------- authorizations

def _pattern(entry: str) -> str:
    # "docs/decisions/X.yaml (append-only)" -> "docs/decisions/X.yaml"
    return entry.split(" (", 1)[0].strip()


def path_matches(path: str, entries) -> bool:
    for entry in entries or []:
        if not isinstance(entry, str):
            continue
        pat = _pattern(entry)
        if not pat:
            continue
        if path == pat or fnmatch.fnmatchcase(path, pat):
            return True
        if pat.endswith("/**") and path.startswith(pat[:-2]):
            return True
    return False


class Authorizations:
    """Authorization records as they stand in one tree (the verified head or the worktree)."""

    def __init__(self, records: dict[str, dict], errors: dict[str, str], allowed: set[str]):
        self.records = records
        self.load_errors = errors
        self.allowed = allowed
        self.revoked_by: dict[str, str] = {}
        for aid, rec in records.items():
            for target in rec.get("revokes") or []:
                self.revoked_by[str(target)] = aid

    @classmethod
    def load(cls, repo: Repo, ref: str | None, allowed: set[str]) -> "Authorizations":
        records, errors = {}, {}
        if ref is None:
            base = repo.root / AUTH_DIR_REL
            items = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(base.glob("*.json"))] if base.is_dir() else []
        else:
            names = repo.git("ls-tree", "--name-only", f"{ref}:{AUTH_DIR_REL}", check=False)
            items = []
            if names.returncode == 0:
                for name in names.stdout.splitlines():
                    if name.endswith(".json"):
                        items.append((name, repo.show(ref, f"{AUTH_DIR_REL}/{name}") or ""))
        for name, text in items:
            stem = name[: -len(".json")]
            try:
                rec = json.loads(text)
            except json.JSONDecodeError:
                errors[stem] = "not valid JSON"
                continue
            if not isinstance(rec, dict) or rec.get("authorization_id") != stem:
                errors[stem] = "authorization_id does not match its file name"
                continue
            records[stem] = rec
        return cls(records, errors, allowed)

    def problem(self, aid: str) -> str | None:
        """Why this id cannot authorize anything, or None if it can."""
        if aid in self.load_errors:
            return f"INVALID_AUTHORIZATION {aid}: {self.load_errors[aid]}"
        rec = self.records.get(aid)
        if rec is None:
            return f"UNKNOWN_AUTHORIZATION {aid}: no {AUTH_DIR_REL}/{aid}.json"
        if rec.get("revoked") is True:
            return f"REVOKED_AUTHORIZATION {aid}: record says revoked"
        if aid in self.revoked_by:
            return f"REVOKED_AUTHORIZATION {aid}: revoked by {self.revoked_by[aid]}"
        if rec.get("authority") not in self.allowed:
            return f"DISALLOWED_AUTHORITY {aid}: authority {rec.get('authority')!r} not in {sorted(self.allowed)}"
        paths = rec.get("authorized_paths")
        if not isinstance(paths, list) or not paths:
            return f"INVALID_AUTHORIZATION {aid}: authorized_paths must be a non-empty list"
        return None

    def covers(self, aid: str, path: str) -> bool:
        if self.problem(aid) is not None:
            return False
        rec = self.records[aid]
        return path_matches(path, rec.get("authorized_paths")) and not path_matches(path, rec.get("excluded_paths"))


# --------------------------------------------------------------------------- config

def load_config(repo: Repo) -> dict:
    path = repo.root / CONFIG_REL
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def allowed_authorities(config: dict) -> set[str]:
    return set(config.get("allowed_authorities") or DEFAULT_ALLOWED) - {"NO_AUTHORITY"}


def nearest_baseline(repo: Repo, config: dict, head: str) -> tuple[str, dict] | None:
    best = None
    for lineage in config.get("lineages") or []:
        sha = repo.resolve(str(lineage.get("baseline_sha", "")))
        if not sha or not repo.is_ancestor(sha, head):
            continue
        distance = int(repo.out("rev-list", "--count", f"{sha}..{head}"))
        if best is None or distance < best[0]:
            best = (distance, sha, lineage)
    return (best[1], best[2]) if best else None


# --------------------------------------------------------------------------- verify

def verify_range(repo: Repo, start: str, head: str, use_worktree: bool, config: dict) -> list[str]:
    findings: list[str] = []
    allowed = allowed_authorities(config)
    head_ledger = repo.show(head, LEDGER_REL)
    if use_worktree:
        path = repo.root / LEDGER_REL
        ledger_text = path.read_text(encoding="utf-8") if path.exists() else ""
        auths = Authorizations.load(repo, None, allowed)
        missing = ledger_lines(head_ledger) - ledger_lines(ledger_text)
        if missing:
            findings.append(f"LEDGER_NOT_APPEND_ONLY worktree: {sum(missing.values())} row(s) committed at HEAD are missing or edited in the working tree")
        changed = repo.out("diff", "--name-status", "--no-renames", head, "--", AUTH_DIR_REL)
        for line in changed.splitlines():
            status, _, p = line.partition("\t")
            if status != "A":
                findings.append(f"AUTHORIZATION_NOT_APPEND_ONLY worktree: {status} {p}")
    else:
        ledger_text = head_ledger or ""
        auths = Authorizations.load(repo, head, allowed)

    rows, bad = parse_rows(ledger_text)
    findings += [f"MALFORMED_ROW {b}" for b in bad]

    changed = repo.out("diff", "--name-status", "--no-renames", start, head, "--", AUTH_DIR_REL)
    for line in changed.splitlines():
        status, _, p = line.partition("\t")
        if status != "A":
            findings.append(f"AUTHORIZATION_NOT_APPEND_ONLY {start[:12]}..{head[:12]}: {status} {p}")

    commits = [x for x in repo.out("rev-list", "--reverse", f"{start}..{head}").splitlines() if x]
    for sha in commits:
        parents = repo.parents(sha)
        # Append-only, commit by commit: no parent's row may vanish or change in the child.
        child_lines = ledger_lines(repo.show(sha, LEDGER_REL))
        for p in parents:
            lost = ledger_lines(repo.show(p, LEDGER_REL)) - child_lines
            if lost:
                findings.append(f"LEDGER_NOT_APPEND_ONLY {sha}: {sum(lost.values())} row(s) of parent {p[:12]} removed or edited")
        files = commit_files(repo, sha)
        if not files:
            continue  # ledger-only commit
        parent = parents[0] if parents else None
        digest = commit_digest(repo, sha)
        bound = bound_rows(rows, sha, parent, digest)
        if not bound:
            findings.append(f"MISSING_ROW {sha}: no ledger row binds to this commit (digest {digest})")
            continue
        for r in bound:
            if r.get("commit_sha") == sha:
                if r.get("commit_diff_sha256") != digest:
                    findings.append(
                        f"DIGEST_MISMATCH {sha}: row ({r.get('kind', '?')}) says {r.get('commit_diff_sha256')!r}, commit is {digest}"
                    )
                if r.get("parent_sha") not in (None, parent):
                    findings.append(f"PARENT_MISMATCH {sha}: row parent {r.get('parent_sha')} is not first parent {parent}")
        ids = sorted({str(i) for r in bound for i in (r.get("authorization_ids") or [])})
        usable = []
        for aid in ids:
            problem = auths.problem(aid)
            if problem:
                findings.append(f"{problem.split(' ', 1)[0]} {sha}: {problem.split(' ', 1)[1]}")
            else:
                usable.append(aid)
        uncovered = [f for f in files if not any(auths.covers(aid, f) for aid in usable)]
        if uncovered:
            shown = ", ".join(uncovered[:8]) + (f" (+{len(uncovered) - 8} more)" if len(uncovered) > 8 else "")
            findings.append(f"UNCOVERED_FILES {sha}: {len(uncovered)} file(s) not covered by {ids or 'no authorization'}: {shown}")
    return findings


def report(mode: str, start: str, head: str, findings: list[str], extra: dict, as_json: bool, repo: Repo) -> int:
    count = int(repo.out("rev-list", "--count", f"{start}..{head}"))
    status = "GREEN" if not findings else "BLOCKED"
    if as_json:
        print(json.dumps({"status": status, "mode": mode, "start": start, "head": head, "commits": count,
                          "findings": findings, **extra}, indent=2, sort_keys=True))
    else:
        print(f"project-truth-ledger {mode}: {status} — {count} commit(s) in {start[:12]}..{head[:12]}")
        for k, v in extra.items():
            print(f"  {k}: {v}")
        for f in findings:
            print(f"  - {f}")
    return 0 if not findings else 1


def cmd_verify(repo: Repo, args) -> int:
    config = load_config(repo)
    head = repo.resolve(args.head)
    if not head:
        print(f"project-truth-ledger: head {args.head!r} not found", file=sys.stderr)
        return 2
    extra: dict = {}
    if args.baseline:
        start = repo.resolve(args.baseline)
        if not start or not repo.is_ancestor(start, head):
            print(f"project-truth-ledger: baseline {args.baseline!r} missing or not an ancestor of {head}", file=sys.stderr)
            return 2
    else:
        found = nearest_baseline(repo, config, head)
        if not found:
            print(f"project-truth-ledger: no enforcement baseline in {CONFIG_REL} is an ancestor of {head}; refusing to guess", file=sys.stderr)
            return 2
        start, lineage = found
        extra["lineage"] = lineage.get("id")
    extra["baseline"] = start
    use_worktree = args.head == "HEAD" and not args.committed
    extra["ledger_source"] = "worktree" if use_worktree else f"{head[:12]}:{LEDGER_REL}"
    findings = verify_range(repo, start, head, use_worktree, config)
    return report("verify", start, head, findings, extra, args.json, repo)


def cmd_verify_pr(repo: Repo, args) -> int:
    config = load_config(repo)
    head = repo.resolve(args.head)
    base = repo.resolve(args.base)
    if not head or not base:
        print(f"project-truth-ledger: base {args.base!r} or head {args.head!r} not found (is the checkout shallow?)", file=sys.stderr)
        return 2
    mb = repo.out("merge-base", base, head)
    start = mb
    extra: dict = {"base": base, "merge_base": mb}
    found = nearest_baseline(repo, config, head)
    if found is None:
        print(f"project-truth-ledger: no enforcement baseline in {CONFIG_REL} is an ancestor of {head}; refusing to guess", file=sys.stderr)
        return 2
    baseline, lineage = found
    extra["lineage"] = lineage.get("id")
    extra["baseline"] = baseline
    if baseline != mb and repo.is_ancestor(mb, baseline):
        gap = int(repo.out("rev-list", "--count", f"{mb}..{baseline}"))
        extra["unenforced_before_baseline"] = f"{gap} commit(s) {mb[:12]}..{baseline[:12]} predate enforcement (see {CONFIG_REL})"
        start = baseline
    findings = verify_range(repo, start, head, use_worktree=False, config=config)
    return report("verify-pr", start, head, findings, extra, args.json, repo)


# --------------------------------------------------------------------------- record

def _merge_heads(repo: Repo) -> list[str]:
    path = Path(repo.out("rev-parse", "--git-path", "MERGE_HEAD"))
    if not path.is_absolute():
        path = repo.root / path
    if not path.exists():
        return []
    return [x.strip() for x in path.read_text().splitlines() if x.strip()]


def _inherited_ids(repo: Repo, rows: list[dict], first: str, others: list[str]) -> set[str]:
    """Authorization ids already recorded for the commits a merge brings in."""
    ids: set[str] = set()
    for other in others:
        for sha in repo.out("rev-list", f"{first}..{other}").splitlines():
            if not commit_files(repo, sha):
                continue
            ps = repo.parents(sha)
            for r in bound_rows(rows, sha, ps[0] if ps else None, commit_digest(repo, sha)):
                ids.update(str(i) for i in r.get("authorization_ids") or [])
    return ids


def _select(auths: Authorizations, files: list[str], explicit: list[str], added_ids: set[str],
            inherited: set[str], existing: set[str]) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Choose authorization ids for files. Returns (new_ids, uncovered, hints).

    Selectable without being named: records whose "reusable" is true, records added by this
    very change, and (for merges) ids already recorded for the merged-in commits. A
    non-reusable record from some other change is never picked up just because its path list
    matches; it is reported as a hint and must be named with --auth.
    """
    covered_by_existing = {f for f in files if any(auths.covers(a, f) for a in existing)}
    pool = list(dict.fromkeys(explicit))
    for aid in sorted(auths.records):
        rec = auths.records[aid]
        if aid in pool or auths.problem(aid):
            continue
        if rec.get("reusable") is True or aid in added_ids or aid in inherited:
            pool.append(aid)
    chosen: list[str] = []
    for aid in pool:
        if aid in existing:
            continue
        # Named or not, an id is added only where it covers a file nothing else covers, so a
        # --range over already-covered commits writes nothing.
        if any(auths.covers(aid, f) for f in files if f not in covered_by_existing and
               not any(auths.covers(c, f) for c in chosen)):
            chosen.append(aid)
    all_ids = set(existing) | set(chosen)
    uncovered = [f for f in files if not any(auths.covers(a, f) for a in all_ids)]
    hints: dict[str, list[str]] = {}
    for f in uncovered:
        for aid in sorted(auths.records):
            if aid not in pool and auths.covers(aid, f):
                hints.setdefault(aid, []).append(f)
    return chosen, uncovered, hints


def _row(repo: Repo, kind: str, source: str, files: list[str], digest: str, parents: list[str],
         commit_sha: str | None, ids: list[str], auths: Authorizations, all_ids: set[str], note: str | None) -> dict:
    covered = [f for f in files if any(auths.covers(a, f) for a in all_ids)]
    row = {
        "schema_version": 2,
        "kind": kind,
        "source": source,
        "repository": "Vanguduza/Van",
        "branch": repo.out("rev-parse", "--abbrev-ref", "HEAD"),
        "parent_sha": parents[0] if parents else None,
        "parents": parents,
        "merge": len(parents) > 1,
        "changed_files": files,
        "commit_diff_sha256": digest,
        "diff_recipe": DIFF_RECIPE,
        "authorization_ids": sorted(ids),
        "authority_classes": sorted({str(auths.records[a].get("authority")) for a in ids if a in auths.records}),
        "covered_files": covered,
        "uncovered_files": [f for f in files if f not in covered],
        "recorded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if commit_sha:
        row["commit_sha"] = commit_sha
    if note:
        row["note"] = note
    return row


def _append(repo: Repo, new_rows: list[dict]) -> None:
    path = repo.root / LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    with path.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        for r in new_rows:
            fh.write(serialize(r) + "\n")


def cmd_record(repo: Repo, args) -> int:
    # Hooks take no arguments, so a committer names a non-reusable record for the commit
    # being made with PROJECT_TRUTH_AUTH=auth-a[,auth-b] git commit ...
    env_ids = [x.strip() for x in os.environ.get("PROJECT_TRUTH_AUTH", "").split(",") if x.strip()]
    args.auth = list(dict.fromkeys([*args.auth, *env_ids]))
    config = load_config(repo)
    auths = Authorizations.load(repo, None, allowed_authorities(config))
    for aid in args.auth:
        problem = auths.problem(aid)
        if problem:
            print(f"project-truth-ledger record: --auth {problem}", file=sys.stderr)
            return 2
    path = repo.root / LEDGER_REL
    rows, _ = parse_rows(path.read_text(encoding="utf-8") if path.exists() else "")
    new_rows: list[dict] = []
    refused = False

    if not args.commit and not args.range:
        # Staged change (pre-commit / pre-merge-commit hook).
        files = staged_files(repo)
        if not files:
            return 0
        status = staged_name_status(repo)
        edited = [f"{s} {p}" for s, p in status if p.startswith(AUTH_DIR_REL + "/") and s != "A"]
        if edited:
            print("project-truth-ledger record: BLOCKED — authorization records are append-only: " + ", ".join(edited), file=sys.stderr)
            return 3
        head = repo.resolve("HEAD")
        parents = ([head] if head else []) + _merge_heads(repo)
        digest = staged_digest(repo)
        if any(not r.get("commit_sha") and r.get("parent_sha") == (parents[0] if parents else None)
               and r.get("commit_diff_sha256") == digest for r in rows):
            print("project-truth-ledger record: staged change already has a row")
            return 0
        added = {p[len(AUTH_DIR_REL) + 1: -5] for s, p in status if s == "A" and p.startswith(AUTH_DIR_REL + "/") and p.endswith(".json")}
        inherited = _inherited_ids(repo, rows, parents[0], parents[1:]) if len(parents) > 1 else set()
        chosen, uncovered, hints = _select(auths, files, args.auth, added, inherited, set())
        if uncovered and not args.allow_uncovered:
            _refuse("staged change", uncovered, hints)
            return 3
        kind = "precommit-staged-diff"
        new_rows.append(_row(repo, kind, f"tools/ci/project_truth_ledger.py record ({args.hook or 'manual'})", files, digest,
                             parents, None, chosen, auths, set(chosen), args.note))
    else:
        targets: list[str] = []
        for c in args.commit:
            sha = repo.resolve(c)
            if not sha:
                print(f"project-truth-ledger record: commit {c!r} not found", file=sys.stderr)
                return 2
            targets.append(sha)
        if args.range:
            targets += [x for x in repo.out("rev-list", "--reverse", args.range).splitlines() if x]
        for sha in dict.fromkeys(targets):
            files = commit_files(repo, sha)
            if not files:
                print(f"skip {sha[:12]}: ledger-only commit")
                continue
            parents = repo.parents(sha)
            digest = commit_digest(repo, sha)
            bound = bound_rows(rows + new_rows, sha, parents[0] if parents else None, digest)
            existing = {str(i) for r in bound for i in (r.get("authorization_ids") or [])}
            added = {p[len(AUTH_DIR_REL) + 1: -5] for s, p in commit_name_status(repo, sha)
                     if s == "A" and p.startswith(AUTH_DIR_REL + "/") and p.endswith(".json")}
            inherited = _inherited_ids(repo, rows + new_rows, parents[0], parents[1:]) if len(parents) > 1 else set()
            chosen, uncovered, hints = _select(auths, files, args.auth, added, inherited, existing)
            if bound and not chosen:
                state = "covered" if not uncovered else f"{len(uncovered)} uncovered, no new authorization selectable"
                print(f"skip {sha[:12]}: row exists ({state})")
                if uncovered:
                    _refuse(sha, uncovered, hints)
                    refused = True
                continue
            if uncovered and not args.allow_uncovered:
                _refuse(sha, uncovered, hints)
                refused = True
                continue
            kind = "supersession" if bound else "integrator-commit-diff"
            note = args.note
            if bound and not note:
                note = f"Adds authorization ids for {sha}; effective authorization is the union over all rows bound to this commit."
            new_rows.append(_row(repo, kind, "tools/ci/project_truth_ledger.py record --commit", files, digest,
                                 parents, sha, chosen, auths, existing | set(chosen), note))
            print(f"{kind} {sha[:12]}: +{chosen}")
    if new_rows:
        _append(repo, new_rows)
        if args.stage:
            repo.git("add", LEDGER_REL)
    if not args.commit and not args.range:
        print(f"project-truth-ledger record: row appended ({', '.join(new_rows[0]['authorization_ids']) or 'no authorization'})")
    return 3 if refused else 0


def _refuse(what: str, uncovered: list[str], hints: dict[str, list[str]]) -> None:
    print(f"project-truth-ledger record: REFUSED {what} — {len(uncovered)} file(s) not covered by a selectable authorization:", file=sys.stderr)
    for f in uncovered:
        print(f"    {f}", file=sys.stderr)
    for aid, fs in hints.items():
        print(f"  hint: non-reusable {aid} lists {len(fs)} of them; pass --auth {aid} only if it really authorizes this change", file=sys.stderr)
    print("  Nothing was written. Add an owner authorization record, name it with --auth, or pass --allow-uncovered to record the gap truthfully (verify will still fail).", file=sys.stderr)


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", help="repository root (default: the git toplevel of the current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="append a row for the staged change or for existing commits")
    rec.add_argument("--commit", action="append", default=[], help="record this existing commit (repeatable)")
    rec.add_argument("--range", help="record every commit in A..B that lacks full coverage")
    rec.add_argument("--auth", action="append", default=[], help="authorization id to cite (repeatable)")
    rec.add_argument("--allow-uncovered", action="store_true", help="write the row even if files stay uncovered")
    rec.add_argument("--stage", action="store_true", help="git add the ledger afterwards (hooks)")
    rec.add_argument("--hook", help="hook name, recorded in the row's source")
    rec.add_argument("--note")

    ver = sub.add_parser("verify", help="verify baseline..HEAD")
    ver.add_argument("--baseline")
    ver.add_argument("--head", default="HEAD")
    ver.add_argument("--committed", action="store_true", help="read the ledger and records from HEAD, not the working tree")
    ver.add_argument("--json", action="store_true")

    pr = sub.add_parser("verify-pr", help="verify merge-base(base, HEAD)..HEAD")
    pr.add_argument("--base", required=True)
    pr.add_argument("--head", default="HEAD")
    pr.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.repo:
        root = Path(args.repo).resolve()
    else:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if top.returncode != 0:
            print("project-truth-ledger: not inside a git repository", file=sys.stderr)
            return 2
        root = Path(top.stdout.strip())
    repo = Repo(root)
    try:
        if args.cmd == "record":
            return cmd_record(repo, args)
        if args.cmd == "verify":
            return cmd_verify(repo, args)
        return cmd_verify_pr(repo, args)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"project-truth-ledger: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
