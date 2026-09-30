# CI install note

GitHub rejected pushing `.github/workflows/ci.yml` because the current credential lacks the `workflow` scope.

Canonical workflow source: `tools/ci/github-actions-ci.yml`

Installer:

```bash
python tools/ci/install_github_workflow.py --apply --commit-push
```

If push is rejected, refresh auth with workflow scope then retry:

```bash
gh auth refresh -h github.com -s workflow
python tools/ci/install_github_workflow.py --apply --commit-push
```

# Project Truth ledger enforcement

Owner decision 2026-09-30 (`docs/decisions/OWNER-DECISION-20260930-OWNER-DERIVED-AND-LEDGER-ENFORCEMENT.md`):
"enforce van's ledger". Checker: `tools/ci/project_truth_ledger.py`. Baselines and the recorded
unenforced history: `registries/project_truth_ledger_baselines.json`.

```bash
python tools/ci/project_truth_ledger.py verify                 # nearest baseline..HEAD
python tools/ci/project_truth_ledger.py verify --baseline <sha>
python tools/ci/project_truth_ledger.py verify-pr --base <sha> # CI: merge-base..HEAD
sh tools/ci/install_project_truth_hooks.sh                     # core.hooksPath=.githooks
```

What `verify` requires of every commit after the baseline (ledger-only commits excepted):

- a row bound to it: `commit_sha` equal to the commit, or, for rows the pre-commit hook wrote
  before the SHA existed, `parent_sha` equal to its first parent and `commit_diff_sha256`
  equal to its digest;
- the digest `sha256(git diff --binary --no-ext-diff --no-renames <first parent> <commit> -- .
  ':(exclude)docs/project-state/LOCAL_CHANGE_LEDGER.jsonl')` matches every row that names the
  commit;
- every changed file is covered by an authorization id on those rows whose record exists in
  `docs/project-state/authorizations/`, is not revoked, has an allowed authority and lists the
  path (exactly or by glob);
- no ledger row and no authorization record is edited or deleted.

**Supersession.** Rows are never edited. A later row for the same commit (kind
`supersession`) adds authorization ids, and a commit's effective authorization is the union
over every row bound to it. It can only add coverage. Authority is withdrawn by revoking the
authorization record, which then fails every commit that relied on it.

**Commits made without the hook** (rebase, cherry-pick, amend, a worktree with no hook, other
units' branches). After integrating them, the integrator appends their rows and commits the
ledger (a ledger-only commit needs no row of its own):

```bash
python tools/ci/project_truth_ledger.py record --range <baseline-or-last-verified>..HEAD --auth <authorization-id> [--auth ...]
git add docs/project-state/LOCAL_CHANGE_LEDGER.jsonl && git commit -m "project-truth: ledger rows for ..."
python tools/ci/project_truth_ledger.py verify
```

`record` writes a row only for commits not already fully covered. It selects on its own only
records marked `reusable`, records added by that same commit, and (for merges) ids already
recorded for the merged-in commits. A non-reusable record for some other change is never
picked up because its path list happens to match; it is printed as a hint and must be named
with `--auth` (or, through the hooks, `PROJECT_TRUTH_AUTH=<id>[,<id>] git commit ...`). If a file stays uncovered, nothing is written and the exit code is 3: add an
owner authorization record first, or pass `--allow-uncovered` to record the gap truthfully
(`verify` will still fail).
