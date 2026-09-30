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
python tools/ci/project_truth_ledger.py verify --committed     # audit: nearest baseline..HEAD, trusts HEAD's records
python tools/ci/project_truth_ledger.py verify --baseline <sha>
python tools/ci/project_truth_ledger.py verify-pr --base <ref> # gate: config, baselines, records from <ref>
sh tools/ci/install_project_truth_hooks.sh                     # core.hooksPath=.githooks
python tests/contracts/ledger_guard_mutations.py               # delete each guard, watch a test fail
```

What is required of every commit after the baseline (ledger-only commits excepted):

- a row bound to it: `commit_sha` equal to the commit, or, for rows the pre-commit hook wrote
  before the SHA existed, `parent_sha` equal to its first parent and `commit_diff_sha256`
  equal to its digest;
- the digest `sha256(git diff --binary --no-ext-diff --no-renames <first parent> <commit> -- .
  ':(exclude)docs/project-state/LOCAL_CHANGE_LEDGER.jsonl')` matches every row that names the
  commit;
- every changed file is covered by an authorization id on those rows whose record exists in the
  trusted tree, is not revoked, has an allowed authority (the config can only narrow
  OWNER_EXPLICIT / OWNER_DERIVED / OWNER_DELEGATED_AUTONOMY), **covers this commit**, and lists
  the path;
- no ledger row is edited or deleted, and no authorization record is modified or deleted,
  checked commit by commit against every parent.

**Commit scope (review I6 M1).** A record with `"reusable": true` covers any commit. Every other
record covers only the commits it declares in `"commit_scope": {"commits": [<full sha>...],
"ranges": ["<sha>..<sha>"]}`, plus merge commits that bring one of those in (the
pre-merge-commit hook sees them through HEAD..MERGE_HEAD). A merge that carries a record file in
unchanged from a merged-in parent needs no authorization for that file; a record the merge
resolution itself creates or alters does. A record written
before scopes were read gets its scope from exactly one `"record_kind": "commit_scope_binding"`
record (`binds: {<id>: <scope>}`); a second binding makes the record cover nothing, and a
binding cannot re-scope a record that declares its own scope. A non-reusable record with no
scope covers nothing.

**Paths.** `*` and `?` stay inside one directory; `**` crosses directories. An entry may end
with `(append-only)` / `(append-only rows)`: it then covers the path only when the commit keeps
the first parent's content as a byte prefix (a deletion or truncation is not covered). Any other
annotation on an authorized path covers nothing. Annotations on `excluded_paths` are comments.

**Trust (review I6 M2).** `verify-pr --base <ref>` reads the config, the baselines and the
authorization records from `<ref>`, not from the PR. A baseline counts only if it is an ancestor
of `<ref>`. A record the PR adds authorizes nothing in the PR (`UNTRUSTED_AUTHORIZATION`). The
base..merge-base history is re-verified against the PR head's records, so a PR that revokes or
conflicts with a record history relies on is refused (`HISTORY_BROKEN_BY_CHANGE`). CI checks the
trusted side (PR base, or the branch head before a push) out into `trusted/`, the head into
`head/`, and runs `python trusted/tools/ci/project_truth_ledger.py --repo head verify-pr`, so a PR
that edits the checker does not run its edit. The job runs on pull requests and on pushes to
`main`, `claude/**`, `forge/**` and the programme branches `gpt/**`.

`verify` without `--base` trusts the tree it audits (HEAD or the working tree). It is the audit
of a protected branch and the developer's local check, not a PR gate.

**Authorization intake and the bootstrap.** A commit whose whole change is adding new record
files is an intake commit: it needs a row (kind `authorization-intake`) but no record authorizes
it. A record becomes usable only once it is on the base branch, and getting it there is the
owner's code-owner review (`.github/CODEOWNERS`). So a unit that needs a new record lands in two
steps:

1. The integrator opens an intake PR onto the programme branch carrying only the record(s) (and
   their rows). `verify-pr` passes it; the owner reviews it as code owner and merges it.
2. The unit's own commits (code, then its intake copy of the record, then the ledger-only rows
   commit) are verified against the new base: `verify-pr --base <programme branch after step 1>`.

One PR carrying both the record and the code it authorizes is refused by `verify-pr`. After both
are on the branch, `verify --committed` at the branch head is GREEN. The record's `commit_scope`
names the unit's code commits, so the code commits exist before the record is written: rows for
them are added afterwards with `record --commit <sha> --auth <id>` (hooks refuse such a commit
unless `PROJECT_TRUTH_ALLOW_UNCOVERED=1`, which records the gap truthfully until the rows land).

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
python tools/ci/project_truth_ledger.py verify --committed
```

`record` writes a row only for commits not already fully covered, and only with ids that cover
the commit (scope included). It selects on its own only records marked `reusable`, records added
by that same commit, and (for merges) ids already recorded for the merged-in commits. A
non-reusable record for some other change is never picked up because its path list happens to
match; it is printed as a hint. If a file stays uncovered, nothing is written and the exit code
is 3: add an owner authorization record naming the commit first, or pass `--allow-uncovered` to
record the gap truthfully (`verify` will still fail).

## Branch protection — external, the owner must enable it

Nothing in this repository can make the checks above binding. Until the owner enables, in
GitHub → Settings → Branches (or Rulesets) for `main` and the programme branches `gpt/**`:

- **Require status checks to pass**: `project-truth-ledger` (job of workflow `van-ci`);
- **Require review from Code Owners** (`.github/CODEOWNERS` names `@Vanguduza` for
  `docs/project-state/authorizations/`, the baselines registry, `tools/ci/`, `.githooks/` and
  `.github/workflows/`);
- **Do not allow bypassing** and block force pushes,

a red ledger check can still be merged and anyone with push access can land a record, a
baseline or a checker change directly. Unit G9a could not verify whether these settings are on.

Two further limits the repository cannot close on its own:

- **`pull_request` runs the PR's workflow file.** GitHub takes the workflow definition for a
  `pull_request` event from the PR's merge ref, so a PR that edits `.github/workflows/van-ci.yml`
  runs its edited job (for example one that runs the PR's own checker). The guard is code-owner
  review of `.github/workflows/`. Moving the ledger job to a `pull_request_target` workflow (the
  base's definition, running only the trusted checker over the head's git objects, no head code
  executed, read-only token) would remove that dependence; that is an owner decision about CI
  privileges and is not made here.
- **The one-time transition.** Until this checker is on the base branch, the trusted checker is
  the previous one, which does not know commit scopes, bindings or intake commits and refuses the
  G9a intake (`INVALID_AUTHORIZATION ... authorized_paths must be a non-empty list` for the
  binding records). The first landing of this change is therefore the owner's explicit act
  (merge with the old check red, or a direct push by the integrator), once. After it, every
  change is judged by this checker from the base.
