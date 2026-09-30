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
    PROJECT_TRUTH_AUTH=<id>[,<id>] names authorizations there and
    PROJECT_TRUTH_ALLOW_UNCOVERED=1 records an uncovered change truthfully. The row is keyed by
    (parent_sha, commit_diff_sha256) because the commit SHA does not exist yet. With
    --commit SHA (repeatable) or --range A..B it records commits that already exist, keyed by
    commit_sha; the integrator uses this for commits made without the hook (rebase,
    cherry-pick, another worktree with no hook installed, amend) and for commits whose
    commit-scoped authorization was recorded after them.
verify [--baseline SHA] [--committed]
    Every commit in baseline..HEAD must have a bound row whose digest matches the commit, and
    every changed file must be covered by a valid authorization the rows name. Without
    --baseline the nearest enforcement baseline in
    `registries/project_truth_ledger_baselines.json` that is an ancestor of HEAD is used. The
    configuration and authorization records are read from HEAD (or the working tree): this mode
    trusts the branch it audits, so it is the audit of a protected branch, not a PR gate.
verify-pr --base REF
    The PR gate. The configuration, the baselines and the authorization records are read from
    the BASE ref, never from the PR: a PR cannot move its own baseline, widen the allowed
    authorities, or authorize itself with a record it adds. Commits in merge-base(REF, HEAD)..HEAD
    (starting no earlier than an enforcement baseline that is an ancestor of REF) are checked
    against the base's records. The base..merge-base history is then re-checked against the PR
    head's records, so a PR that revokes or conflicts with a record history relies on is refused.
    CI runs the BASE ref's copy of this script (`--repo <pr checkout>`), so a PR that edits the
    checker does not run its own edit.

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
      * exists in the trusted tree (the base ref for verify-pr; HEAD for verify),
      * is not revoked and has an authority in the allowed set (the configured list, which can
        only narrow OWNER_EXPLICIT / OWNER_DERIVED / OWNER_DELEGATED_AUTONOMY),
      * covers commit C: a record with "reusable": true covers any commit; any other record
        covers only the commits its "commit_scope" declares ({"commits": [sha, ...]} and/or
        {"ranges": ["A..B", ...]}, full SHAs, ranges as `git rev-list A..B`), or, for a record
        written before commit_scope existed, the scope that exactly one
        "record_kind": "commit_scope_binding" record assigns to it. A merge commit is covered
        when it brings in (C^1..C) a commit of the scope. A non-reusable record with no scope
        covers nothing. A merge that carries a record file in unchanged from a merged-in parent
        needs no authorization for that file (its intake is verified where it was made).
      * lists the path in authorized_paths and not in excluded_paths. Globs: `*` and `?` do
        not cross `/`, `**` does. An entry may carry one trailing annotation:
        "(append-only)" / "(append-only rows)" cover the path only when the commit keeps the
        first parent's bytes as a prefix of the new content (and does not delete it); any other
        annotation on an authorized path covers nothing. Annotations on excluded_paths are
        comments (an exclusion only narrows).
    Authorization records are append-only commit by commit: a commit may add record files but
    never modify or delete one, relative to each of its parents.

Authorization intake
    A commit whose whole change is the addition of new authorization record files is an intake
    commit. It needs a bound row, but no record authorizes it: a record cannot authorize its own
    addition, and a record added by a PR authorizes nothing in that PR. The record becomes
    usable only once it is on the base ref, which is what the code-owner review on
    `docs/project-state/authorizations/**` (.github/CODEOWNERS) guards. Bootstrap: merge the
    intake commit first, then verify the commits it authorizes against the new base.

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
BINDING_KIND = "commit_scope_binding"
APPEND_ONLY_ANNOTATIONS = frozenset({"append-only", "append-only rows"})
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DIFF_RECIPE = (
    "sha256(git diff --binary --no-ext-diff --no-renames <parent_sha> <commit_sha> -- . "
    "':(exclude)docs/project-state/LOCAL_CHANGE_LEDGER.jsonl'); first parent for merges"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RANGE_RE = re.compile(r"^([0-9a-f]{40})\.\.([0-9a-f]{40})$")
ANNOTATION_RE = re.compile(r"^(.*?)\s+\(([^()]*)\)\s*$")
# Pin the diff-header options a user's config could change, so the digest depends on the
# change and not on whoever computed it. These are git's defaults.
GIT_PIN = [
    "-c", "diff.noprefix=false",
    "-c", "diff.mnemonicPrefix=false",
    "-c", "diff.relative=false",
    "-c", "core.quotePath=true",
    "-c", "color.ui=never",
]
INDEX = ":"  # pseudo-ref: the staged content


class Repo:
    def __init__(self, root: Path):
        self.root = root
        self._introduced: dict[str, frozenset[str]] = {}

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
        spec = f":{path}" if ref == INDEX else f"{ref}:{path}"
        proc = self.git("show", spec, check=False)
        return proc.stdout if proc.returncode == 0 else None

    def show_bytes(self, ref: str | None, path: str) -> bytes | None:
        if ref is None:
            return None
        spec = f":{path}" if ref == INDEX else f"{ref}:{path}"
        proc = self.git("show", spec, check=False, binary=True)
        return proc.stdout if proc.returncode == 0 else None

    def introduced(self, sha: str) -> frozenset[str]:
        """Commits a merge brings in: C^1..C without C itself (empty for non-merges)."""
        if sha not in self._introduced:
            ps = self.parents(sha)
            if len(ps) < 2:
                self._introduced[sha] = frozenset()
            else:
                got = self.out("rev-list", f"{ps[0]}..{sha}").split()
                self._introduced[sha] = frozenset(x for x in got if x != sha)
        return self._introduced[sha]


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


def is_record_path(p: str) -> bool:
    return p.startswith(AUTH_DIR_REL + "/")


def intake_ids(name_status: list[tuple[str, str]]) -> list[str] | None:
    """The record ids a pure intake change adds, or None if the change is anything else."""
    if not name_status:
        return None
    ids = []
    for status, p in name_status:
        if status != "A" or not is_record_path(p) or "/" in p[len(AUTH_DIR_REL) + 1:] or not p.endswith(".json"):
            return None  # GUARD:intake-pure-only
        ids.append(p[len(AUTH_DIR_REL) + 1: -len(".json")])
    return ids


def merged_in_records(repo: Repo, parents: list[str], files: list[str], new_ref: str) -> set[str]:
    """Record files a merge adds that arrive unchanged from a merged-in parent.

    The commit that added such a record on the other side is verified on its own (as an intake
    commit, or covered like any change); the merge only carries it over. A record the merge
    resolution itself creates or alters is not in this set and must be covered."""
    out = set()
    if len(parents) < 2:
        return out
    for f in files:
        if not is_record_path(f) or repo.show_bytes(parents[0], f) is not None:
            continue
        new = repo.show_bytes(new_ref, f)
        if new is not None and any(repo.show_bytes(p, f) == new for p in parents[1:]):  # GUARD:merged-record-unchanged
            out.add(f)
    return out


def record_changes_vs(repo: Repo, parent: str, sha: str) -> list[str]:
    """Authorization-record paths `sha` modifies or deletes relative to `parent` (additions are fine)."""
    out = repo.out("diff", "--name-status", "--no-renames", parent, sha, "--", AUTH_DIR_REL)
    bad = []
    for line in out.splitlines():
        status, _, p = line.partition("\t")
        if status != "A":
            bad.append(f"{status} {p}")
    return bad


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


# --------------------------------------------------------------------------- paths

def _glob_regex(pat: str) -> re.Pattern:
    out, i, n = [], 0, len(pat)
    while i < n:
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")  # zero or more whole directories
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(path: str, pat: str) -> bool:
    """`*` and `?` stay inside one path segment; `**` crosses `/`."""
    if path == pat:
        return True
    return _glob_regex(pat).match(path) is not None


def parse_entry(entry: str) -> tuple[str, str | None]:
    """"docs/X.yaml (append-only)" -> ("docs/X.yaml", "append-only"); no annotation -> None."""
    m = ANNOTATION_RE.match(entry)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return entry.strip(), None


def is_append_only(old: bytes | None, new: bytes | None) -> bool:
    if new is None:
        return False  # deleted
    return old is None or new.startswith(old)


# --------------------------------------------------------------------------- authorizations

def _resolve_scope(repo: Repo, spec) -> tuple[frozenset[str] | None, str | None]:
    if not isinstance(spec, dict) or not spec:
        return None, "commit scope must be an object with 'commits' and/or 'ranges'"
    unknown = set(spec) - {"commits", "ranges", "note", "derivation"}
    if unknown:
        return None, f"commit scope has unknown keys {sorted(unknown)}"
    commits: set[str] = set()
    for sha in spec.get("commits") or []:
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            return None, f"commit scope entry {sha!r} is not a full commit SHA"
        commits.add(sha)
    for r in spec.get("ranges") or []:
        m = RANGE_RE.match(r) if isinstance(r, str) else None
        if not m:
            return None, f"commit scope range {r!r} is not <full sha>..<full sha>"
        if not repo.resolve(m.group(1)) or not repo.resolve(m.group(2)):
            return None, f"commit scope range {r!r} names a commit this repository does not have"
        commits.update(x for x in repo.out("rev-list", r).split() if x)
    if not commits:
        return None, "commit scope is empty"
    return frozenset(commits), None


class Authorizations:
    """Authorization records as they stand in one trusted tree (a ref or the worktree)."""

    def __init__(self, repo: Repo, records: dict[str, dict], bindings: dict[str, dict], errors: dict[str, str],
                 allowed: set[str], source: str):
        self.repo = repo
        self.records = records
        self.bindings = bindings
        self.load_errors = errors
        self.allowed = allowed
        self.source = source
        self.revoked_by: dict[str, str] = {}
        for aid, rec in records.items():
            for target in rec.get("revokes") or []:
                self.revoked_by[str(target)] = aid
        self.global_findings: list[str] = []
        self.scope: dict[str, frozenset[str]] = {}
        self.scope_errors: dict[str, str] = {}
        self._resolve_scopes()

    @classmethod
    def load(cls, repo: Repo, ref: str | None, allowed: set[str]) -> "Authorizations":
        records, bindings, errors = {}, {}, {}
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
            if rec.get("record_kind") == BINDING_KIND:
                bindings[stem] = rec
            else:
                records[stem] = rec
        return cls(repo, records, bindings, errors, allowed, "worktree" if ref is None else ref)

    def _resolve_scopes(self) -> None:
        claims: dict[str, list[tuple[str, object]]] = collections.defaultdict(list)
        for bid, b in sorted(self.bindings.items()):
            why = None
            if b.get("revoked") is True or bid in self.revoked_by:
                continue
            if b.get("authority") not in self.allowed:
                why = f"authority {b.get('authority')!r} not in {sorted(self.allowed)}"
            elif not isinstance(b.get("binds"), dict) or not b["binds"]:
                why = "'binds' must be a non-empty object {authorization_id: commit scope}"
            if why:
                self.global_findings.append(f"INVALID_SCOPE_BINDING {bid}: {why}")
                continue
            for target, spec in b["binds"].items():
                rec = self.records.get(target)
                if rec is None:
                    self.global_findings.append(f"INVALID_SCOPE_BINDING {bid}: binds {target}, which is not an authorization record here")
                elif rec.get("reusable") is True or "commit_scope" in rec:  # GUARD:binding-cannot-rescope
                    self.global_findings.append(f"INVALID_SCOPE_BINDING {bid}: {target} declares its own scope (or is reusable); a binding cannot re-scope it")
                else:
                    claims[target].append((bid, spec))
        for aid, rec in self.records.items():
            if rec.get("reusable") is True:
                continue
            if "commit_scope" in rec:
                scope, err = _resolve_scope(self.repo, rec["commit_scope"])
            elif len(claims.get(aid, [])) > 1:  # GUARD:binding-conflict
                scope, err = None, f"bound by more than one scope binding ({', '.join(b for b, _ in claims[aid])}); refusing to choose"
            elif claims.get(aid):
                bid, spec = claims[aid][0]
                scope, err = _resolve_scope(self.repo, spec)
                if err:
                    err = f"scope binding {bid}: {err}"
            else:
                scope, err = None, "non-reusable record declares no commit_scope and no scope binding names it; it covers nothing"
            if err:
                self.scope_errors[aid] = err
            else:
                self.scope[aid] = scope  # type: ignore[assignment]

    def problem(self, aid: str) -> str | None:
        """Why this id cannot authorize anything, or None if it can."""
        if aid in self.load_errors:
            return f"INVALID_AUTHORIZATION {aid}: {self.load_errors[aid]}"
        if aid in self.bindings:
            return f"NOT_AN_AUTHORIZATION {aid}: a commit_scope_binding record authorizes no files"
        rec = self.records.get(aid)
        if rec is None:
            return f"UNKNOWN_AUTHORIZATION {aid}: no {AUTH_DIR_REL}/{aid}.json in the trusted tree ({self.source})"
        if rec.get("revoked") is True:
            return f"REVOKED_AUTHORIZATION {aid}: record says revoked"
        if aid in self.revoked_by:
            return f"REVOKED_AUTHORIZATION {aid}: revoked by {self.revoked_by[aid]}"
        if rec.get("authority") not in self.allowed:
            return f"DISALLOWED_AUTHORITY {aid}: authority {rec.get('authority')!r} not in {sorted(self.allowed)}"
        paths = rec.get("authorized_paths")
        if not isinstance(paths, list) or not paths:
            return f"INVALID_AUTHORIZATION {aid}: authorized_paths must be a non-empty list"
        if aid in self.scope_errors:  # GUARD:unscoped
            return f"UNSCOPED_AUTHORIZATION {aid}: {self.scope_errors[aid]}"
        return None

    def in_scope(self, aid: str, sha: str | None, introduced: frozenset[str] | None = None) -> bool:
        """Does record `aid` cover commit `sha`? For a staged change (sha None) only a reusable
        record does, or, for a staged merge, a record whose scope holds a commit the merge brings
        in (`introduced`, from HEAD..MERGE_HEAD)."""
        rec = self.records[aid]
        if rec.get("reusable") is True:
            return True
        scope = self.scope.get(aid, frozenset())
        if sha is None:
            return bool(introduced and introduced & scope)
        if sha in scope:
            return True
        return bool(self.repo.introduced(sha) & scope)

    def path_cover(self, aid: str, path: str, old: bytes | None, new: bytes | None) -> tuple[bool, str | None]:
        """Does this record's path list cover `path` for a change old -> new? (covered, note)."""
        rec = self.records[aid]
        for entry in rec.get("excluded_paths") or []:
            if isinstance(entry, str) and glob_match(path, parse_entry(entry)[0]):
                return False, None
        note = None
        for entry in rec.get("authorized_paths") or []:
            if not isinstance(entry, str):
                continue
            pat, ann = parse_entry(entry)
            if not pat or not glob_match(path, pat):  # GUARD:glob
                continue
            if ann is None:
                return True, None
            if ann in APPEND_ONLY_ANNOTATIONS:
                if is_append_only(old, new):  # GUARD:append-only
                    return True, None
                note = f"{aid} allows {path} only as '({ann})' and this change does not keep the old content as a prefix"
            else:  # GUARD:unrecognised-annotation
                note = f"{aid} lists {path} with annotation '({ann})', which this checker cannot enforce; the entry covers nothing"
        return False, note

    def covers(self, aid: str, path: str, sha: str | None = None, old: bytes | None = None, new: bytes | None = None,
               introduced: frozenset[str] | None = None) -> bool:
        if self.problem(aid) is not None or not self.in_scope(aid, sha, introduced):
            return False
        return self.path_cover(aid, path, old, new)[0]


# --------------------------------------------------------------------------- config

def load_config(repo: Repo, ref: str | None = None) -> dict:
    if ref is not None:
        text = repo.show(ref, CONFIG_REL)
        return json.loads(text) if text else {}
    path = repo.root / CONFIG_REL
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def allowed_authorities(config: dict) -> set[str]:
    # The configuration can narrow the owner authority classes, never add to them.
    return set(config.get("allowed_authorities") or DEFAULT_ALLOWED) & set(DEFAULT_ALLOWED)  # GUARD:allowed-narrow-only


def nearest_baseline(repo: Repo, config: dict, head: str, anchor: str | None = None) -> tuple[str, dict] | None:
    """Nearest lineage baseline that is an ancestor of head (and of `anchor`, the trusted base, if given)."""
    best = None
    for lineage in config.get("lineages") or []:
        sha = repo.resolve(str(lineage.get("baseline_sha", "")))
        if not sha or not repo.is_ancestor(sha, head):
            continue
        if anchor is not None and not repo.is_ancestor(sha, anchor):  # GUARD:baseline-ancestor-of-base
            continue
        distance = int(repo.out("rev-list", "--count", f"{sha}..{head}"))
        if best is None or distance < best[0]:
            best = (distance, sha, lineage)
    return (best[1], best[2]) if best else None


# --------------------------------------------------------------------------- verify

def verify_range(repo: Repo, start: str, head: str, auths: Authorizations, rows: list[dict],
                 head_ids: set[str] | None = None) -> list[str]:
    """Check every commit in start..head against `auths` (the trusted records) and `rows`."""
    findings: list[str] = list(auths.global_findings)
    commits = [x for x in repo.out("rev-list", "--reverse", f"{start}..{head}").splitlines() if x]
    for sha in commits:
        parents = repo.parents(sha)
        # Append-only, commit by commit: no parent's row may vanish or change in the child.
        child_lines = ledger_lines(repo.show(sha, LEDGER_REL))
        for p in parents:
            lost = ledger_lines(repo.show(p, LEDGER_REL)) - child_lines
            if lost:  # GUARD:ledger-append-only
                findings.append(f"LEDGER_NOT_APPEND_ONLY {sha}: {sum(lost.values())} row(s) of parent {p[:12]} removed or edited")
        # The same rule for authorization records: a commit may add record files, never
        # modify or delete one, relative to each of its parents.
        for p in parents or [EMPTY_TREE]:
            bad = record_changes_vs(repo, p, sha)
            if bad:  # GUARD:record-append-only
                findings.append(f"AUTHORIZATION_NOT_APPEND_ONLY {sha}: {', '.join(bad)} (vs parent {p[:12]})")
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
                if r.get("commit_diff_sha256") != digest:  # GUARD:digest
                    findings.append(
                        f"DIGEST_MISMATCH {sha}: row ({r.get('kind', '?')}) says {r.get('commit_diff_sha256')!r}, commit is {digest}"
                    )
                if r.get("parent_sha") not in (None, parent):
                    findings.append(f"PARENT_MISMATCH {sha}: row parent {r.get('parent_sha')} is not first parent {parent}")
        status = commit_name_status(repo, sha)
        added = intake_ids(status)
        if added is not None:  # GUARD:intake-exemption
            # Intake: the commit only adds record files. No record authorizes its own addition;
            # the records become usable once they are on the base ref (code-owner review).
            for aid in added:
                text = repo.show(sha, f"{AUTH_DIR_REL}/{aid}.json") or ""
                try:
                    rec = json.loads(text)
                except json.JSONDecodeError:
                    rec = None
                if not isinstance(rec, dict) or rec.get("authorization_id") != aid:
                    findings.append(f"INVALID_AUTHORIZATION_INTAKE {sha}: {aid}.json is not a record whose authorization_id matches its file name")
            continue
        ids = sorted({str(i) for r in bound for i in (r.get("authorization_ids") or [])})
        carried = merged_in_records(repo, parents, files, sha)
        usable, notes = [], []
        for aid in ids:
            problem = auths.problem(aid)
            if problem:
                code, _, detail = problem.partition(" ")
                if code == "UNKNOWN_AUTHORIZATION" and head_ids is not None and aid in head_ids:
                    code, detail = "UNTRUSTED_AUTHORIZATION", (
                        f"{aid}: added by this change, not present on the trusted base ({auths.source}); "
                        "a record cannot authorize the change that adds it (merge the record first)")
                findings.append(f"{code} {sha}: {detail}")
            elif not auths.in_scope(aid, sha):  # GUARD:scope
                notes.append(f"{aid} is not reusable and {sha[:12]} is not in its commit scope")
            else:
                usable.append(aid)
        uncovered = []
        for f in files:
            if f in carried:
                continue
            old = repo.show_bytes(parent, f)
            new = repo.show_bytes(sha, f)
            ok = False
            for aid in usable:
                hit, note = auths.path_cover(aid, f, old, new)
                if hit:
                    ok = True
                    break
                if note:
                    notes.append(note)
            if not ok:
                uncovered.append(f)
        if uncovered:
            shown = ", ".join(uncovered[:8]) + (f" (+{len(uncovered) - 8} more)" if len(uncovered) > 8 else "")
            why = f" [{'; '.join(dict.fromkeys(notes))}]" if notes else ""
            findings.append(f"UNCOVERED_FILES {sha}: {len(uncovered)} file(s) not covered by {ids or 'no authorization'}: {shown}{why}")
    return findings


def worktree_findings(repo: Repo, head_ledger: str | None, ledger_text: str) -> list[str]:
    findings = []
    missing = ledger_lines(head_ledger) - ledger_lines(ledger_text)
    if missing:
        findings.append(f"LEDGER_NOT_APPEND_ONLY worktree: {sum(missing.values())} row(s) committed at HEAD are missing or edited in the working tree")
    changed = repo.out("diff", "--name-status", "--no-renames", "HEAD", "--", AUTH_DIR_REL)
    for line in changed.splitlines():
        status, _, p = line.partition("\t")
        if status != "A":
            findings.append(f"AUTHORIZATION_NOT_APPEND_ONLY worktree: {status} {p}")
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
    head = repo.resolve(args.head)
    if not head:
        print(f"project-truth-ledger: head {args.head!r} not found", file=sys.stderr)
        return 2
    use_worktree = args.head == "HEAD" and not args.committed
    config = load_config(repo, None if use_worktree else head)
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
    extra["ledger_source"] = "worktree" if use_worktree else f"{head[:12]}:{LEDGER_REL}"
    extra["trusted_records"] = "worktree" if use_worktree else head[:12]
    allowed = allowed_authorities(config)
    head_ledger = repo.show(head, LEDGER_REL)
    findings: list[str] = []
    if use_worktree:
        path = repo.root / LEDGER_REL
        ledger_text = path.read_text(encoding="utf-8") if path.exists() else ""
        auths = Authorizations.load(repo, None, allowed)
        findings += worktree_findings(repo, head_ledger, ledger_text)
    else:
        ledger_text = head_ledger or ""
        auths = Authorizations.load(repo, head, allowed)
    rows, bad = parse_rows(ledger_text)
    findings += [f"MALFORMED_ROW {b}" for b in bad]
    findings += verify_range(repo, start, head, auths, rows)
    return report("verify", start, head, findings, extra, args.json, repo)


def cmd_verify_pr(repo: Repo, args) -> int:
    head = repo.resolve(args.head)
    base = repo.resolve(args.base)
    if not head or not base:
        print(f"project-truth-ledger: base {args.base!r} or head {args.head!r} not found (is the checkout shallow?)", file=sys.stderr)
        return 2
    # Everything that decides what counts comes from the base ref, not from the PR.
    trusted = base  # GUARD:trust-base
    config = load_config(repo, trusted)
    mb = repo.out("merge-base", base, head)
    start = mb
    extra: dict = {"base": base, "merge_base": mb, "trusted_config_and_records": trusted[:12]}
    found = nearest_baseline(repo, config, head, anchor=base)
    if found is None:
        print(f"project-truth-ledger: no enforcement baseline in {base[:12]}:{CONFIG_REL} is an ancestor of both the base and {head[:12]}; refusing to guess", file=sys.stderr)
        return 2
    baseline, lineage = found
    extra["lineage"] = lineage.get("id")
    extra["baseline"] = baseline
    if baseline != mb and repo.is_ancestor(mb, baseline):
        gap = int(repo.out("rev-list", "--count", f"{mb}..{baseline}"))
        extra["unenforced_before_baseline"] = f"{gap} commit(s) {mb[:12]}..{baseline[:12]} predate enforcement (see {CONFIG_REL})"
        start = baseline
    allowed = allowed_authorities(config)
    rows, bad = parse_rows(repo.show(head, LEDGER_REL))
    findings = [f"MALFORMED_ROW {b}" for b in bad]
    head_auths = Authorizations.load(repo, head, allowed)
    base_auths = Authorizations.load(repo, trusted, allowed)
    head_ids = set(head_auths.records) | set(head_auths.bindings) | set(head_auths.load_errors)
    findings += verify_range(repo, start, head, base_auths, rows, head_ids=head_ids)
    # History the base already carries must still verify under the records the PR leaves
    # behind: a PR that revokes, or adds a conflicting binding for, a record history relies on
    # breaks the branch and is refused here.
    if baseline != start and repo.is_ancestor(baseline, start):
        hist = verify_range(repo, baseline, start, head_auths, rows)
        hist = [f for f in hist if f not in head_auths.global_findings]
        findings += [f"HISTORY_BROKEN_BY_CHANGE {f}" for f in hist]  # GUARD:history
        extra["history_rechecked"] = f"{baseline[:12]}..{start[:12]} against the PR head's records"
    findings += [f for f in head_auths.global_findings if f not in findings]
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


class _Change:
    """A change to cover: a commit (sha) or the staged index (sha None)."""

    def __init__(self, repo: Repo, sha: str | None, parent: str | None, files: list[str], merge_heads: list[str] | None = None):
        self.sha, self.parent, self.files = sha, parent, files
        self.introduced = frozenset(x for mh in merge_heads or [] for x in repo.out("rev-list", f"{parent}..{mh}").split())
        ps = repo.parents(sha) if sha else ([parent] if parent else []) + list(merge_heads or [])
        self.carried = merged_in_records(repo, ps, files, INDEX if sha is None else sha)
        self.need = [f for f in files if f not in self.carried]  # what an authorization must cover
        new_ref = INDEX if sha is None else sha
        self.content = {f: (repo.show_bytes(parent, f), repo.show_bytes(new_ref, f)) for f in files}

    def covered(self, auths: Authorizations, aid: str, f: str) -> bool:
        if f in self.carried:
            return True
        old, new = self.content[f]
        return auths.covers(aid, f, self.sha, old, new, self.introduced)


def _select(auths: Authorizations, change: _Change, explicit: list[str], added_ids: set[str],
            inherited: set[str], existing: set[str]) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """Choose authorization ids for a change. Returns (new_ids, uncovered, hints).

    Selectable without being named: records whose "reusable" is true, records added by this
    very change, and (for merges) ids already recorded for the merged-in commits; each still
    covers only the commits in its scope. A non-reusable record from some other change is
    never picked up just because its path list matches; it is reported as a hint and must be
    named with --auth.
    """
    files = change.need
    covered_by_existing = {f for f in files if any(change.covered(auths, a, f) for a in existing)}
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
        if any(change.covered(auths, aid, f) for f in files if f not in covered_by_existing and
               not any(change.covered(auths, c, f) for c in chosen)):
            chosen.append(aid)
    all_ids = set(existing) | set(chosen)
    uncovered = [f for f in files if not any(change.covered(auths, a, f) for a in all_ids)]
    hints: dict[str, list[str]] = {}
    for f in uncovered:
        for aid in sorted(auths.records):
            if aid not in pool and not auths.problem(aid) and auths.path_cover(aid, f, *change.content[f])[0]:
                hints.setdefault(aid, []).append(f)
    return chosen, uncovered, hints


def _row(repo: Repo, kind: str, source: str, change: _Change, digest: str, parents: list[str],
         ids: list[str], auths: Authorizations, all_ids: set[str], note: str | None) -> dict:
    files = change.files
    covered = [f for f in files if any(change.covered(auths, a, f) for a in all_ids)] if kind != "authorization-intake" else []
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
        "uncovered_files": [] if kind == "authorization-intake" else [f for f in files if f not in covered],
        "recorded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if change.sha:
        row["commit_sha"] = change.sha
    if note:
        row["note"] = note
    return row


INTAKE_NOTE = ("Authorization intake: this change only adds authorization record files. No record authorizes its own "
               "addition; the ids listed are the records added, for reference. They become usable once on the base ref.")


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
    if os.environ.get("PROJECT_TRUTH_ALLOW_UNCOVERED") == "1":
        args.allow_uncovered = True
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
        edited = [f"{s} {p}" for s, p in status if is_record_path(p) and s != "A"]
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
        change = _Change(repo, None, parents[0] if parents else None, files, parents[1:])
        intake = intake_ids(status)
        if intake is not None:
            new_rows.append(_row(repo, "authorization-intake", f"tools/ci/project_truth_ledger.py record ({args.hook or 'manual'})",
                                 change, digest, parents, intake, auths, set(), args.note or INTAKE_NOTE))
        else:
            added = {p[len(AUTH_DIR_REL) + 1: -5] for s, p in status if s == "A" and is_record_path(p) and p.endswith(".json")}
            inherited = _inherited_ids(repo, rows, parents[0], parents[1:]) if len(parents) > 1 else set()
            chosen, uncovered, hints = _select(auths, change, args.auth, added, inherited, set())
            if uncovered and not args.allow_uncovered:
                _refuse("staged change", uncovered, hints)
                return 3
            new_rows.append(_row(repo, "precommit-staged-diff", f"tools/ci/project_truth_ledger.py record ({args.hook or 'manual'})",
                                 change, digest, parents, chosen, auths, set(chosen), args.note))
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
            change = _Change(repo, sha, parents[0] if parents else None, files)
            status = commit_name_status(repo, sha)
            intake = intake_ids(status)
            if intake is not None:
                if bound:
                    print(f"skip {sha[:12]}: intake commit already has a row")
                    continue
                new_rows.append(_row(repo, "authorization-intake", "tools/ci/project_truth_ledger.py record --commit", change,
                                     digest, parents, intake, auths, set(), args.note or INTAKE_NOTE))
                print(f"authorization-intake {sha[:12]}: adds {intake}")
                continue
            existing = {str(i) for r in bound for i in (r.get("authorization_ids") or [])}
            added = {p[len(AUTH_DIR_REL) + 1: -5] for s, p in status if s == "A" and is_record_path(p) and p.endswith(".json")}
            inherited = _inherited_ids(repo, rows + new_rows, parents[0], parents[1:]) if len(parents) > 1 else set()
            chosen, uncovered, hints = _select(auths, change, args.auth, added, inherited, existing)
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
            new_rows.append(_row(repo, kind, "tools/ci/project_truth_ledger.py record --commit", change, digest,
                                 parents, chosen, auths, existing | set(chosen), note))
            print(f"{kind} {sha[:12]}: +{chosen}")
    if new_rows:
        _append(repo, new_rows)
        if args.stage:
            repo.git("add", LEDGER_REL)
    if not args.commit and not args.range:
        print(f"project-truth-ledger record: row appended ({new_rows[0]['kind']}; {', '.join(new_rows[0]['authorization_ids']) or 'no authorization'})")
    return 3 if refused else 0


def _refuse(what: str, uncovered: list[str], hints: dict[str, list[str]]) -> None:
    print(f"project-truth-ledger record: REFUSED {what} — {len(uncovered)} file(s) not covered by a selectable authorization:", file=sys.stderr)
    for f in uncovered:
        print(f"    {f}", file=sys.stderr)
    for aid, fs in hints.items():
        print(f"  hint: non-reusable {aid} lists {len(fs)} of them; pass --auth {aid} only if it really authorizes this change "
              "(it covers only the commits in its commit scope)", file=sys.stderr)
    print("  Nothing was written. Add an owner authorization record whose commit_scope names this commit, then record it "
          "with --auth; or pass --allow-uncovered (hooks: PROJECT_TRUTH_ALLOW_UNCOVERED=1) to record the gap truthfully "
          "(verify will still fail until a record covers it).", file=sys.stderr)


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

    ver = sub.add_parser("verify", help="verify baseline..HEAD (audit of a protected branch; trusts HEAD's records)")
    ver.add_argument("--baseline")
    ver.add_argument("--head", default="HEAD")
    ver.add_argument("--committed", action="store_true", help="read the ledger, config and records from HEAD, not the working tree")
    ver.add_argument("--json", action="store_true")

    pr = sub.add_parser("verify-pr", help="PR gate: verify merge-base(base, HEAD)..HEAD against the base ref's config and records")
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
