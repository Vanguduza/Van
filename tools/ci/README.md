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
