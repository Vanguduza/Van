#!/bin/sh
# Install VAN's Project Truth ledger hooks: point core.hooksPath at the tracked .githooks/.
#
#   sh tools/ci/install_project_truth_hooks.sh           # this clone (all its worktrees)
#   sh tools/ci/install_project_truth_hooks.sh --check   # report, change nothing
#
# core.hooksPath lives in the clone's shared config, so every worktree of the clone uses it. A
# worktree whose checkout has no .githooks/ then runs no hooks at all (git ignores a missing
# hook), and hooks formerly in .git/hooks stop running. To try the hooks on one command only:
#   git -c core.hooksPath=.githooks commit ...
set -eu
top=$(git rev-parse --show-toplevel)
cd "$top"
current=$(git config --get core.hooksPath || true)
if [ "${1:-}" = "--check" ]; then
  if [ "$current" = ".githooks" ]; then echo "INSTALLED core.hooksPath=.githooks"; exit 0; fi
  echo "NOT_INSTALLED core.hooksPath=${current:-<unset>}"; exit 1
fi
for h in .githooks/pre-commit .githooks/pre-merge-commit; do
  [ -f "$h" ] || { echo "missing $h" >&2; exit 2; }
  chmod +x "$h"
done
git config core.hooksPath .githooks
echo "INSTALLED core.hooksPath=.githooks (was ${current:-<unset>})"
