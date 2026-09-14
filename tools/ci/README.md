# CI install note

GitHub rejected pushing `.github/workflows/ci.yml` because the current credential lacks the `workflow` scope.

Canonical workflow source: `tools/ci/github-actions-ci.yml`

To enable Actions, copy it into `.github/workflows/ci.yml` with a token that has `workflow` scope:
`gh auth refresh -h github.com -s workflow`
then restore the path and push.
